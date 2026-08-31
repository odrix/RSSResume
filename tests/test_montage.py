"""Le montage d'une journée en un seul texte, et ce qu'il refuse d'y mettre.

Ce que ces tests protègent, dans l'ordre d'importance :

- le montage est un SECOND passage : il enchaîne des résumés déjà écrits, et ce qui
  n'est pas dans ce qu'on lui donne ne doit pas pouvoir en sortir ;
- les phrases de plomberie — « Aucun article retenu sur 3 (seuil 7) » — ne partent
  jamais à la voix, alors que la phrase d'une catégorie CERT-FR sans correspondance,
  elle, est un vrai résultat qui doit s'entendre ;
- une journée déjà payée ne se perd pas sur le dernier appel : sans fournisseur comme
  après un échec, l'assemblage local prend la suite et `origine` le dit.
"""

import datetime as dt
import pathlib
import unittest
from unittest import mock

from rssresume.llm import LLMError
from rssresume.models import (
    ORIGINE_ASSEMBLAGE,
    ORIGINE_MONTAGE,
    Article,
    CategoryDigest,
    Ephemeride,
)
from rssresume.montage import MontageService

ENVOI = dt.date(2026, 8, 31)
EPHEMERIDE = Ephemeride(
    jour=ENVOI,
    fete="saint Aristide",
    texte="1991 — l'Ukraine proclame son indépendance.",
    origine="table",
)


def article(titre="Un titre"):
    return Article(
        item_id=titre,
        category="Cyber",
        title=titre,
        url="https://ex.test/a",
        published_at=dt.datetime(2026, 8, 30, 8, 0),
        feed_title="Flux A",
        content_text="",
    )


def racontee(categorie, resume, retenus=1):
    """Une catégorie qui a quelque chose à dire : pas de marqueur, un vrai résumé."""
    return CategoryDigest(
        category=categorie,
        articles=[article()],
        summary_text=resume,
        selected=[article() for _ in range(retenus)],
    )


def muette(categorie, phrase="Aucun article retenu sur 3 (seuil 7)."):
    """Une catégorie sans rien : c'est son marqueur qui la désigne, pas sa sélection."""
    return CategoryDigest(
        category=categorie,
        articles=[],
        summary_text=phrase,
        marker_path=pathlib.Path("news.no-article"),
    )


class FakeProvider:
    """Un fournisseur qui note ce qu'on lui demande, et rend ce qu'on lui a dit de rendre."""

    name = "faux"

    def __init__(self, texte="Le montage du jour.", erreur=None):
        self.appels = []
        self._texte = texte
        self._erreur = erreur

    def model(self, action):
        return f"modele-{action}"

    def write_montage(self, sections, jour, muettes, language="fr", profil=None, prenom=""):
        self.appels.append(
            {
                "sections": sections,
                "jour": jour,
                "muettes": muettes,
                "language": language,
                "profil": profil,
                "prenom": prenom,
            }
        )
        if self._erreur:
            raise self._erreur
        return self._texte


class CeQuiPartAuModeleTests(unittest.TestCase):
    def test_the_categories_keep_the_order_they_were_given(self):
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE,
            [racontee("Cyber", "Une faille sur Traefik."), racontee("Marché", "Un rachat.")],
        )

        appel, = provider.appels
        self.assertEqual(
            [
                {"categorie": "Cyber", "resume": "Une faille sur Traefik."},
                {"categorie": "Marché", "resume": "Un rachat."},
            ],
            appel["sections"],
        )

    def test_the_opening_line_carries_the_day_the_letter_is_sent(self):
        """La même date, la même fête et le même fait que l'introduction de l'email."""
        provider = FakeProvider()

        MontageService(provider).ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        jour = provider.appels[0]["jour"]
        self.assertEqual(
            "Lundi 31 août 2026, saint Aristide. "
            "1991 — l'Ukraine proclame son indépendance.",
            jour,
        )

    def test_a_day_without_an_ephemeride_opens_on_nothing_rather_than_on_a_wrong_date(self):
        provider = FakeProvider()

        MontageService(provider).ecrire(None, [racontee("Cyber", "Une faille.")])

        self.assertEqual("", provider.appels[0]["jour"])

    def test_the_plumbing_sentence_of_an_empty_category_never_reaches_the_voice(self):
        """« Aucun article retenu sur 3 (seuil 7) » lu à voix haute serait un défaut."""
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille."), muette("News")]
        )

        appel, = provider.appels
        self.assertEqual(["Cyber"], [section["categorie"] for section in appel["sections"]])
        self.assertEqual(["News"], appel["muettes"])

    def test_a_certfr_category_that_matches_nothing_is_still_told(self):
        """Elle n'a pas de marqueur et sa phrase est un résultat, pas de la plomberie :
        « sept avis, aucun ne touche la stack » est exactement ce qu'on veut entendre."""
        provider = FakeProvider()
        avis = CategoryDigest(
            category="CERT-FR",
            articles=[article()],
            summary_text="7 avis CERT-FR aujourd'hui, aucun ne touche la stack.",
        )

        MontageService(provider).ecrire(EPHEMERIDE, [avis])

        appel, = provider.appels
        self.assertEqual(["CERT-FR"], [section["categorie"] for section in appel["sections"]])
        self.assertEqual([], appel["muettes"])

    def test_the_profile_and_the_first_name_travel_with_the_call(self):
        provider = FakeProvider()

        MontageService(provider, language="fr", profil="Vigneronne", prenom="Adrien").ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille.")]
        )

        appel, = provider.appels
        self.assertEqual("Vigneronne", appel["profil"])
        self.assertEqual("Adrien", appel["prenom"])
        self.assertEqual("fr", appel["language"])


class ResultatTests(unittest.TestCase):
    def test_the_text_of_the_model_is_kept_with_its_origin(self):
        montage = MontageService(FakeProvider("Bonjour Adrien. Voici la journée.")).ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille.")]
        )

        self.assertEqual("Bonjour Adrien. Voici la journée.", montage.texte)
        self.assertEqual(ORIGINE_MONTAGE, montage.origine)
        self.assertIsNone(montage.audio_path)

    def test_a_day_with_nothing_to_say_produces_no_text_and_calls_nobody(self):
        """Une salutation suivie d'un silence est pire qu'une pièce jointe absente."""
        provider = FakeProvider()

        montage = MontageService(provider).ecrire(EPHEMERIDE, [muette("News")])

        self.assertEqual("", montage.texte)
        self.assertEqual([], provider.appels)


class AssemblageTests(unittest.TestCase):
    """Le repli : la journée est déjà payée, elle ne se perd pas sur le dernier appel."""

    def test_without_a_provider_the_summaries_are_laid_end_to_end(self):
        montage = MontageService(prenom="Adrien").ecrire(
            EPHEMERIDE,
            [racontee("Cyber", "Une faille sur Traefik."), racontee("Marché", "Un rachat.")],
        )

        self.assertEqual(ORIGINE_ASSEMBLAGE, montage.origine)
        self.assertIn("Bonjour Adrien.", montage.texte)
        self.assertIn("saint Aristide", montage.texte)
        self.assertIn("Une faille sur Traefik.", montage.texte)
        self.assertIn("Un rachat.", montage.texte)

    def test_without_a_first_name_nobody_is_greeted_by_name(self):
        montage = MontageService().ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        self.assertIn("Bonjour.", montage.texte)

    def test_a_failed_call_falls_back_instead_of_losing_the_day(self):
        provider = FakeProvider(erreur=LLMError("503"))

        montage = MontageService(provider, prenom="Adrien").ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille sur Traefik.")]
        )

        self.assertEqual(ORIGINE_ASSEMBLAGE, montage.origine)
        self.assertIn("Une faille sur Traefik.", montage.texte)

    def test_the_silent_categories_are_named_once_at_the_end(self):
        montage = MontageService().ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille."), muette("News"), muette("Culture")]
        )

        self.assertIn("Rien à signaler du côté de : News, Culture.", montage.texte)


class PromptTests(unittest.TestCase):
    """Ce que le prompt système porte, et ce qu'il interdit."""

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_the_system_prompt_carries_the_profile_and_the_first_name(self):
        from rssresume.llm.prompts import montage_system

        prompt = montage_system("Vigneronne en Anjou", "Adrien")

        self.assertIn("Vigneronne en Anjou", prompt)
        self.assertIn("Adrien", prompt)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_without_a_first_name_the_prompt_names_nobody(self):
        from rssresume.llm.prompts import montage_system

        self.assertNotIn("s'appelle", montage_system("Vigneronne en Anjou", "   "))

    def test_the_user_prompt_forbids_reformulating_the_versions(self):
        """La consigne cardinale : c'est ici qu'un « 7.4.5 » devient un « 7.4 »."""
        from rssresume.llm.prompts import montage_user

        prompt = montage_user([{"categorie": "Cyber", "resume": "x"}], "Lundi.", [], "fr")

        self.assertIn("caractère pour caractère", prompt)
        # Les données de la journée sont dans la zone encadrée, comme partout ailleurs.
        self.assertIn("<<<DONNEES ARTICLES>>>", prompt)


if __name__ == "__main__":
    unittest.main()
