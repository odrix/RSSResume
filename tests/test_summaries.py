import dataclasses
import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume import cve
from rssresume.models import Article, Note
from rssresume.profil import DEFAULT_PROFIL
from rssresume.summaries import SummaryGenerator
from support import make_config


def make_article(title="Titre", content="Contenu test pour le résumé.", url="https://example.com/a"):
    return Article(
        item_id="item-1",
        category="Tech",
        title=title,
        url=url,
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text=content,
    )


def make_llm_config(tmpdir, profil=None):
    return dataclasses.replace(
        make_config(tmpdir),
        llm_base_url="https://api.example/v1",
        llm_api_key="key",
        summary_model="gpt-4o-mini",
        **({"profil": profil} if profil else {}),
    )


class SummaryGeneratorTests(unittest.TestCase):
    def test_fallback_summary_is_audio_friendly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = SummaryGenerator(make_config(tmpdir)).summarize("Tech", [make_article()])

            self.assertIn("Résumé du jour pour la catégorie Tech", summary)
            self.assertTrue(summary.endswith("Bonne journée."))
            # Ni puces ni retours à la ligne : le texte part en synthèse vocale d'un trait.
            self.assertNotIn("\n", summary)
            self.assertNotIn("- ", summary)

    def test_summary_without_article_needs_no_backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = SummaryGenerator(make_config(tmpdir)).summarize("Tech", [])

            self.assertEqual("Aucun nouvel article aujourd'hui dans la catégorie Tech.", summary)


class PromptTests(unittest.TestCase):
    def _call(self, articles, notes=None, profil=None):
        """Renvoie l'appel au fournisseur : (…, system, user, …)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("rssresume.summaries.llm.chat", return_value="résumé") as chat:
                SummaryGenerator(make_llm_config(tmpdir, profil)).summarize("Tech", articles, notes)
        return chat.call_args.args

    def _prompt(self, articles, notes=None):
        return self._call(articles, notes)[4]

    def _system(self, articles, profil=None):
        return self._call(articles, profil=profil)[3]

    def test_system_prompt_carries_the_relevance_profile(self):
        """Sans le profil, le résumeur écrivait bien pour l'oreille mais pour personne."""
        system = self._system([make_article()])

        self.assertIn(DEFAULT_PROFIL, system)
        self.assertIn("Privilégie ce qui a des conséquences concrètes pour ce profil", system)
        self.assertIn("ce qui change, à quelle échéance", system)
        # La contrainte de lisibilité vocale est conservée.
        self.assertIn("lu à voix haute", system)
        self.assertIn("phrases enchaînées", system)

    def test_an_injected_profile_replaces_the_default_one(self):
        """Ouvrir l'outil à un autre profil ne doit demander que ce texte."""
        system = self._system([make_article()], profil="Vigneronne en Anjou, bio depuis 2019.")

        self.assertIn("Vigneronne en Anjou, bio depuis 2019.", system)
        self.assertNotIn(DEFAULT_PROFIL, system)

    def test_prompt_carries_no_url(self):
        prompt = self._prompt([make_article(url="https://example.com/secret-path")])

        self.assertNotIn("example.com", prompt)
        self.assertNotIn("secret-path", prompt)

    def test_prompt_forbids_lists_and_boilerplate_conclusion(self):
        prompt = self._prompt([make_article()])

        self.assertIn("prose continue", prompt)
        self.assertIn("Jamais de liste à puces", prompt)
        self.assertIn("Pas de conclusion passe-partout", prompt)

    def test_prompt_requires_merging_articles_on_the_same_event(self):
        """Trois dépêches sur le même incident font un sujet, pas trois passages."""
        prompt = self._prompt([make_article(), make_article(title="Autre titre")])

        self.assertIn("UN SEUL sujet", prompt)
        self.assertIn("Ne produis jamais deux passages distincts pour le même fait", prompt)
        # Fusionner garde ce que chaque dépêche apporte de plus, sans les nommer.
        self.assertIn("ce que chaque article apporte de plus", prompt)

    def test_prompt_never_names_the_publishing_media(self):
        """Le média n'est pas l'information : ni consigne de le citer, ni flux dans le contexte."""
        prompt = self._prompt([make_article(url="https://example.com/secret-path")])

        self.assertIn("Ne nomme jamais le média", prompt)
        self.assertIn("ni sous la forme « selon X »", prompt)
        # Le nom du flux ne part pas au modèle : ce qu'il n'a pas, il ne peut pas le dire.
        self.assertNotIn('"feed"', prompt)
        self.assertNotIn("Feed", prompt)

    def test_an_organisation_acting_in_the_news_is_not_a_source(self):
        """Taire les médias ne doit pas faire taire l'ANSSI quand c'est elle qui publie l'avis."""
        prompt = self._prompt([make_article()])

        self.assertIn("n'est pas une source", prompt)
        self.assertIn("l'ANSSI qui publie un avis", prompt)

    def test_prompt_asks_for_a_spoken_rhythm(self):
        """Voix plate à l'écoute : c'est la phrase écrite qu'il faut rythmer, pas le TTS."""
        prompt = self._prompt([make_article()])

        self.assertIn("alterne des phrases courtes et des phrases longues", prompt)
        self.assertIn("Pas de parenthèses", prompt)
        self.assertIn("Varie les débuts de phrase", prompt)

    def test_prompt_opens_and_closes_on_the_day_itself(self):
        """Une phrase d'accueil et une de sortie, jugées sur la journée, pour un seul auditeur."""
        prompt = self._prompt([make_article()])

        self.assertIn("Ouvre par UNE seule phrase courte", prompt)
        self.assertIn("elle n'est jamais la même d'un jour à l'autre", prompt)
        self.assertIn("Termine par UNE seule phrase courte", prompt)
        self.assertIn("qui découle des sujets du jour", prompt)
        # Une seule personne écoute : ni « bonjour à tous », ni « nous ».
        self.assertIn("Tu t'adresses à une seule personne", prompt)
        # Les deux phrases ne doivent pas se recouvrir.
        self.assertIn("ne doivent pas dire la même chose", prompt)

    def test_each_cve_stays_a_subject_of_its_own(self):
        """La règle de fusion écrasait les CVE entre elles : on y perdait produit et version."""
        prompt = self._prompt([make_article(title="CVE-2026-1234 : RCE dans X")])

        self.assertIn("UNE vulnérabilité = UN sujet à elle seule", prompt)
        self.assertIn("les paliers de longueur ci-dessus ne s'appliquent pas ici", prompt)
        # L'ordre des faits attendus, qui est ce qui rend la CVE utile à l'écoute.
        self.assertIn(
            "l'identifiant, le produit et les versions touchés, ce que la faille permet, "
            "si elle est déjà exploitée, et ce qu'il y a à faire",
            prompt,
        )
        # Le nom commercial exact et les versions : c'est là-dessus que l'auditeur
        # décide s'il est concerné, et c'est ce qui manquait à l'écoute.
        self.assertIn("sous leur nom commercial exact", prompt)
        self.assertIn("la plage touchée ET la version corrigée", prompt)
        self.assertIn("quand l'avis ne donne pas les versions", prompt)

    def test_merging_applies_to_the_same_fact_not_the_same_topic(self):
        prompt = self._prompt([make_article()])

        self.assertIn("Le même FAIT, pas le même thème", prompt)
        self.assertIn("deux vulnérabilités différentes", prompt)

    def test_cve_article_is_enriched_before_the_prompt(self):
        article = make_article(title="CVE-2026-1234 : RCE dans X", content="Un avis.")
        with mock.patch.object(cve, "fetch_detail", return_value="Versions 1.0 à 1.4 touchées.") as fetch:
            prompt = self._prompt([article])

        fetch.assert_called_once_with("https://example.com/a")
        self.assertIn("Versions 1.0 à 1.4 touchées.", prompt)


    def test_angle_and_thematique_are_handed_to_the_summarizer(self):
        """Le scoring les a déjà payés : c'est le contexte qui manquait au résumé."""
        notes = {"item-1": Note(9, "reglementaire", "Impose une échéance à l'éditeur.")}

        prompt = self._prompt([make_article()], notes)

        self.assertIn("Impose une échéance à l'éditeur.", prompt)
        self.assertIn("reglementaire", prompt)
        self.assertIn("Le champ « angle »", prompt)

    def test_a_cached_note_carries_no_angle(self):
        """Un score relu des tags revient sans angle : le champ est simplement omis."""
        prompt = self._prompt([make_article()], {"item-1": Note(9, "cyber")})

        self.assertIn('"thematique": "cyber"', prompt)
        self.assertNotIn('"angle"', prompt)


if __name__ == "__main__":
    unittest.main()
