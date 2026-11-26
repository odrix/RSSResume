"""Le montage d'une journée en un seul texte, et ce qu'il refuse d'y mettre.

Ce que ces tests protègent, dans l'ordre d'importance :

- le montage part des SUJETS de toutes les catégories, remis dans un seul ordre : c'est
  la différence entre un seul fichier et un seul récit, et l'ordre des dossiers FreshRSS
  ne doit plus décider de ce qu'on entend en premier ;
- la phrase d'une catégorie déterministe est relayée telle quelle, jamais refaite : la
  faire réécrire par un modèle réintroduirait l'invention là où `certfr/` l'a écartée ;
- les phrases de plomberie, « Aucun article retenu sur 3 (seuil 7) » : ne partent
  jamais à la voix ;
- une journée déjà payée ne se perd pas sur le dernier appel : sans fournisseur comme
  après un échec, l'assemblage local prend la suite et `origine` le dit.
"""

import datetime as dt
import pathlib
import unittest
from unittest import mock

from rssresume.certfr import Stack
from rssresume.llm import LLMError
from rssresume.models import (
    ORIGINE_ASSEMBLAGE,
    ORIGINE_MONTAGE,
    Article,
    CategoryDigest,
    Ephemeride,
    Note,
)
from rssresume.montage import MontageService
from rssresume.profil import SECURITE_PAR_DEFAUT, Securite

ENVOI = dt.date(2026, 8, 31)
EPHEMERIDE = Ephemeride(
    jour=ENVOI,
    fete="saint Aristide",
    texte="1991, l'Ukraine proclame son indépendance.",
    origine="table",
)


def article(titre="Un titre", contenu="Le corps de l'article."):
    return Article(
        item_id=titre,
        category="Cyber",
        title=titre,
        url="https://ex.test/a",
        published_at=dt.datetime(2026, 8, 30, 8, 0),
        feed_title="Flux A",
        content_text=contenu,
    )


def racontee(categorie, resume, sujets=None, contenus=None):
    """Une catégorie résumée : pas de marqueur, des articles retenus et leurs notes.

    `sujets` est une suite de (titre, score, thematique), c'est tout ce dont l'ordre du
    jour a besoin. Par défaut, un seul sujet dont le titre porte la catégorie, pour que
    deux catégories montées dans le même test ne partagent pas un identifiant.
    """
    sujets = sujets or ((f"Sujet {categorie}", 7, "cyber"),)
    contenus = contenus or {}
    articles = [
        article(titre, contenus.get(titre, "Le corps de l'article."))
        for titre, _, _ in sujets
    ]
    notes = {
        titre: Note(score=score, thematique=theme, angle=f"Ce que {titre} change.")
        for titre, score, theme in sujets
    }
    return CategoryDigest(
        category=categorie,
        articles=articles,
        summary_text=resume,
        selected=articles,
        notes=notes,
    )


def deterministe(categorie, phrase):
    """Une catégorie routée hors du pipeline LLM : sa phrase est déjà écrite."""
    return CategoryDigest(
        category=categorie,
        articles=[article(f"Avis {categorie}")],
        summary_text=phrase,
        deterministe=True,
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

    def write_montage(
        self,
        sujets,
        jour,
        constats,
        muettes,
        language="fr",
        profil=None,
        prenom="",
        stack_declaree=False,
        securite=SECURITE_PAR_DEFAUT,
    ):
        self.appels.append(
            {
                "sujets": sujets,
                "jour": jour,
                "constats": constats,
                "muettes": muettes,
                "language": language,
                "profil": profil,
                "prenom": prenom,
                "stack_declaree": stack_declaree,
                "securite": securite,
            }
        )
        if self._erreur:
            raise self._erreur
        return self._texte


class OrdreDuJourTests(unittest.TestCase):
    """L'ordre du récit se refait à l'échelle de la journée, pas à celle des dossiers."""

    def test_the_best_scored_subject_opens_the_day_whatever_its_category(self):
        """Le défaut qu'on corrige : la catégorie décidait de ce qu'on entendait en premier."""
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE,
            [
                racontee("Marché", "Un rachat.", (("Un rachat", 7, "marche"),)),
                racontee("Cyber", "Une faille.", (("Une faille critique", 10, "cyber"),)),
            ],
        )

        appel, = provider.appels
        self.assertEqual(
            ["Une faille critique", "Un rachat"], [sujet["title"] for sujet in appel["sujets"]]
        )

    def test_related_subjects_from_two_categories_end_up_side_by_side(self):
        """« Sujet connexe » : la thématique est déjà notée, elle ne coûte aucun appel."""
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE,
            [
                racontee("Cyber", "x", (("Faille grave", 10, "cyber"), ("NIS2", 8, "reglementaire"))),
                racontee("Veille", "y", (("DORA", 9, "reglementaire"), ("Faille mineure", 7, "cyber"))),
            ],
        )

        appel, = provider.appels
        # Le groupe cyber ouvre, il porte le meilleur score, puis le réglementaire
        # d'un bloc, ses deux articles réunis alors qu'ils venaient de deux catégories.
        self.assertEqual(
            ["Faille grave", "Faille mineure", "DORA", "NIS2"],
            [sujet["title"] for sujet in appel["sujets"]],
        )

    def test_a_subject_carries_its_angle_and_its_theme(self):
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE, [racontee("Cyber", "x", (("Une faille", 9, "cyber"),))]
        )

        sujet, = provider.appels[0]["sujets"]
        self.assertEqual(9, sujet["score"])
        self.assertEqual("cyber", sujet["thematique"])
        self.assertEqual("Ce que Une faille change.", sujet["angle"])
        self.assertEqual("Le corps de l'article.", sujet["content"])

    def test_no_category_name_travels_with_a_subject(self):
        """Elle n'a plus rien à décider une fois l'ordre posé, et le modèle l'annoncerait."""
        provider = FakeProvider()

        MontageService(provider).ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        sujet, = provider.appels[0]["sujets"]
        self.assertNotIn("categorie", sujet)
        # Ni URL ni nom de flux : ce qui n'est pas dans le contexte ne peut pas être prononcé.
        self.assertNotIn("url", sujet)
        self.assertNotIn("source", sujet)


class CeQuiPartAuModeleTests(unittest.TestCase):
    def test_the_opening_line_carries_the_day_the_letter_is_sent(self):
        """La même date, la même fête et le même fait que l'introduction de l'email."""
        provider = FakeProvider()

        MontageService(provider).ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        jour = provider.appels[0]["jour"]
        self.assertEqual(
            "Lundi 31 août 2026, saint Aristide. "
            "1991, l'Ukraine proclame son indépendance.",
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
        self.assertEqual(["Sujet Cyber"], [sujet["title"] for sujet in appel["sujets"]])
        self.assertEqual([], appel["constats"])
        self.assertEqual(["News"], appel["muettes"])

    def test_a_certfr_category_is_relayed_as_a_constat_never_as_a_subject(self):
        """Sa phrase est produite sans modèle : la refaire dire ferait revenir l'invention."""
        provider = FakeProvider()
        phrase = "7 avis CERT-FR aujourd'hui, aucun ne touche la stack."

        MontageService(provider).ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille."), deterministe("CERT-FR", phrase)]
        )

        appel, = provider.appels
        self.assertEqual([phrase], appel["constats"])
        # Ses avis ne sont pas notés : ils n'ont rien à faire valoir dans l'ordre du jour.
        self.assertEqual(["Sujet Cyber"], [sujet["title"] for sujet in appel["sujets"]])
        self.assertEqual([], appel["muettes"])

    def test_a_certfr_category_alone_still_produces_a_text(self):
        """Une journée où seul le déterministe a parlé : un constat sans aucun sujet."""
        provider = FakeProvider()

        MontageService(provider).ecrire(
            EPHEMERIDE, [deterministe("CERT-FR", "7 avis, 2 touchent la stack.")]
        )

        appel, = provider.appels
        self.assertEqual([], appel["sujets"])
        self.assertEqual(["7 avis, 2 touchent la stack."], appel["constats"])

    def test_the_profile_and_the_first_name_travel_with_the_call(self):
        provider = FakeProvider()

        MontageService(provider, language="fr", profil="Vigneronne", prenom="Adrien").ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille.")]
        )

        appel, = provider.appels
        self.assertEqual("Vigneronne", appel["profil"])
        self.assertEqual("Adrien", appel["prenom"])
        self.assertEqual("fr", appel["language"])


class StackTests(unittest.TestCase):
    """La stack ne trie rien ici : elle règle le détail donné sur les versions d'une CVE."""

    STACK = Stack.declaree(["Keycloak"])

    def test_a_touched_component_is_named_on_the_subject(self):
        provider = FakeProvider()

        MontageService(provider, stack=self.STACK).ecrire(
            EPHEMERIDE,
            [
                racontee(
                    "Cyber",
                    "x",
                    (("CVE-2026-1234", 9, "cyber"),),
                    contenus={"CVE-2026-1234": "Keycloak 26.0 à 26.3 sont touchées."},
                )
            ],
        )

        sujet, = provider.appels[0]["sujets"]
        self.assertEqual(["Keycloak"], sujet["stack"])
        self.assertTrue(provider.appels[0]["stack_declaree"])

    def test_an_untouched_advisory_carries_no_stack_field(self):
        provider = FakeProvider()

        MontageService(provider, stack=self.STACK).ecrire(
            EPHEMERIDE,
            [
                racontee(
                    "Cyber",
                    "x",
                    (("CVE-2026-9999", 9, "cyber"),),
                    contenus={"CVE-2026-9999": "FortiOS 7.4 est touché."},
                )
            ],
        )

        sujet, = provider.appels[0]["sujets"]
        self.assertNotIn("stack", sujet)
        # La graduation reste annoncée : c'est elle qui allège cette CVE-là.
        self.assertTrue(provider.appels[0]["stack_declaree"])

    def test_without_a_declared_stack_nothing_is_graduated(self):
        provider = FakeProvider()

        MontageService(provider).ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        self.assertFalse(provider.appels[0]["stack_declaree"])

    def test_the_service_passes_the_regime_to_the_provider(self):
        provider = FakeProvider()

        MontageService(provider, securite=Securite.CURIEUX).ecrire(
            EPHEMERIDE, [racontee("Cyber", "Une faille.")]
        )

        self.assertIs(Securite.CURIEUX, provider.appels[0]["securite"])

    def test_without_a_regime_the_service_asks_for_the_default(self):
        provider = FakeProvider()

        MontageService(provider).ecrire(EPHEMERIDE, [racontee("Cyber", "Une faille.")])

        self.assertIs(Securite.EXPLOITANT, provider.appels[0]["securite"])


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

        prompt = montage_user([{"title": "x", "content": "y"}], "Lundi.", [], [], "fr")

        self.assertIn("caractère pour caractère", prompt)
        # Les données de la journée sont dans la zone encadrée, comme partout ailleurs.
        self.assertIn("<<<DONNEES ARTICLES>>>", prompt)

    def test_the_user_prompt_holds_the_order_and_hides_the_categories(self):
        """L'ordre est fait par le code : le modèle ne le refait pas et ne le défait pas."""
        from rssresume.llm.prompts import montage_user

        prompt = montage_user([{"title": "x", "content": "y"}], "Lundi.", [], [], "fr")

        self.assertIn("dans l'ordre exact où ils doivent être racontés", prompt)
        self.assertIn("ne nomme aucune catégorie, n'annonce aucune rubrique", prompt)
        # La fusion des doublons se fait ici, et c'est ce qui rapproche deux catégories.
        self.assertIn("Le même FAIT, pas le même thème", prompt)

    def test_the_user_prompt_relays_the_constats_without_rewriting_them(self):
        from rssresume.llm.prompts import montage_user

        prompt = montage_user([], "Lundi.", ["7 avis, aucun ne touche la stack."], [], "fr")

        self.assertIn("Le bloc « constats » porte des phrases DÉJÀ écrites", prompt)
        self.assertIn("jamais les reformuler", prompt)
        self.assertIn("7 avis, aucun ne touche la stack.", prompt)

    def test_the_user_prompt_grades_depth_on_each_subject_score(self):
        """Le palier de volume fixe l'enveloppe ; le score de chaque sujet la répartit."""
        from rssresume.llm.prompts import montage_user

        prompt = montage_user([{"title": "x", "content": "y", "score": 9}], "Lundi.", [], [], "fr")

        self.assertIn("Chaque sujet porte un champ « score »", prompt)
        self.assertIn('"score": 9', prompt)

    def test_the_user_prompt_grades_the_cve_detail_on_the_declared_stack(self):
        from rssresume.llm.prompts import montage_user

        sujets = [{"title": "x", "content": "y"}]

        self.assertIn(
            "la plage touchée ET la version corrigée",
            montage_user(sujets, "Lundi.", [], [], "fr"),
        )
        graduee = montage_user(sujets, "Lundi.", [], [], "fr", stack_declaree=True)
        self.assertIn("Le champ « stack » nomme les composants", graduee)
        self.assertIn("AUCUN numéro de version, aucune plage, aucune branche", graduee)

    def test_the_user_prompt_follows_the_security_regime(self):
        """Le même choix que le résumé de catégorie : l'œil et l'oreille disent pareil."""
        from rssresume.llm import prompts

        sujets = [{"title": "x", "content": "y"}]
        for securite in Securite:
            for declaree in (False, True):
                with self.subTest(securite=securite, stack_declaree=declaree):
                    prompt = prompts.montage_user(
                        sujets, "Lundi.", [], [], "fr", declaree, securite
                    )
                    self.assertIn(prompts.cve_instruction(declaree, securite), prompt)

        decideur = prompts.montage_user(sujets, "Lundi.", [], [], "fr", False, Securite.DECIDEUR)
        self.assertIn(prompts.CVE_SANS_VERSIONS_INSTRUCTION, decideur)
        self.assertNotIn("la plage touchée ET la version corrigée", decideur)
        curieux = prompts.montage_user(sujets, "Lundi.", [], [], "fr", True, Securite.CURIEUX)
        self.assertIn(prompts.CVE_CURIEUX_INSTRUCTION, curieux)
        self.assertIn(prompts.CVE_CURIEUX_STACK_INSTRUCTION, curieux)
        self.assertNotIn(prompts.CVE_INSTRUCTION, curieux)

    def test_montage_without_regime_is_unchanged(self):
        from rssresume.llm.prompts import montage_user

        sujets = [{"title": "x", "content": "y"}]
        for declaree in (False, True):
            with self.subTest(stack_declaree=declaree):
                self.assertEqual(
                    montage_user(sujets, "Lundi.", [], [], "fr", declaree, Securite.EXPLOITANT),
                    montage_user(sujets, "Lundi.", [], [], "fr", stack_declaree=declaree),
                )


if __name__ == "__main__":
    unittest.main()
