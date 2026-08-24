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
        # Fusionner ne veut pas dire taire les sources qui ont couvert le fait.
        self.assertIn("les sources qui l'ont couvert", prompt)

    def test_prompt_attributes_subjects_to_the_feed_name_not_the_url(self):
        """Le nom du flux est dans le contexte, l'URL non : elle serait inventée."""
        prompt = self._prompt([make_article(url="https://example.com/secret-path")])

        self.assertIn("le nom du flux entre parenthèses", prompt)
        self.assertIn("Jamais d'URL", prompt)
        # Le nom du flux, lui, doit bien être fourni au modèle : c'est ce qu'il doit citer.
        self.assertIn('"feed": "Feed"', prompt)

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
