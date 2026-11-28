"""Chargement du document de profil, et effets de son injection.

Un seul fichier porte tout ce qui est personnel : le critère de pertinence, la stack
surveillée, le destinataire du digest. Ces tests protègent les deux extrémités, que le
document soit lu en entier, et qu'un document fautif fasse échouer le lancement plutôt
que de laisser noter une journée contre un critère qui n'est pas celui qu'on croit.
"""

import datetime as dt
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.certfr import StackError
from rssresume.axes import Axes, CLE_AXES
from rssresume.llm.prompts import article_system, scoring_system
from tests.support import empreinte
from rssresume.models import Article
from rssresume.categories import Catalogue, CategorieCatalogue
from rssresume.profil import (
    CLE_CATEGORIES,
    CLE_EMAIL,
    CLE_FLUX_EXCLUS,
    CLE_ID,
    CLE_PRENOM,
    CLE_PROFIL,
    CLE_SECURITE,
    CLE_STACK,
    DEFAULT_PROFIL,
    ENV_PROFIL,
    ENV_PROFIL_FILE,
    ChampInvalide,
    FluxExclus,
    Securite,
    load_profil,
    profil_depuis_dict,
)

AUTRE_PROFIL = "Vigneronne en Anjou, bio depuis 2019. Veille : météo, phytosanitaire, export."


def charge(contenu):
    """Écrit un document de profil et rend le `Profil` chargé depuis lui.

    Le document passe par un vrai fichier et par la variable d'environnement : c'est le
    chemin qu'emprunte le lancement, et ce sont ses erreurs que ces tests protègent.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        fichier = pathlib.Path(tmpdir) / "profile.json"
        if not isinstance(contenu, str):
            contenu = json.dumps(contenu, ensure_ascii=False)
        fichier.write_text(contenu, encoding="utf-8")

        with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
            return load_profil()


class LoadProfilTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_without_configuration_the_default_profile_applies(self):
        self.assertEqual(DEFAULT_PROFIL, load_profil().texte)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_an_explicit_profile_wins(self):
        self.assertEqual(AUTRE_PROFIL, load_profil(AUTRE_PROFIL).texte)

    @mock.patch.dict(os.environ, {ENV_PROFIL: f"  {AUTRE_PROFIL}  "}, clear=True)
    def test_the_inline_variable_is_read_and_trimmed(self):
        self.assertEqual(AUTRE_PROFIL, load_profil().texte)

    @mock.patch.dict(os.environ, {ENV_PROFIL: "profil de l'environnement"}, clear=True)
    def test_an_explicit_profile_beats_the_environment(self):
        self.assertEqual(AUTRE_PROFIL, load_profil(AUTRE_PROFIL).texte)

    def test_a_profile_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "profil.txt"
            fichier.write_text(AUTRE_PROFIL, encoding="utf-8")

            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                self.assertEqual(AUTRE_PROFIL, load_profil().texte)

    def test_the_inline_variable_beats_the_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "profil.txt"
            fichier.write_text("profil du fichier", encoding="utf-8")
            env = {ENV_PROFIL: AUTRE_PROFIL, ENV_PROFIL_FILE: str(fichier)}

            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(AUTRE_PROFIL, load_profil().texte)

    @mock.patch.dict(os.environ, {ENV_PROFIL_FILE: "/introuvable/profil.txt"}, clear=True)
    def test_an_unreadable_profile_file_raises(self):
        """Noter toute une journée contre le mauvais critère, sans rien dire, serait pire."""
        with self.assertRaises(ValueError):
            load_profil()

    def test_an_empty_profile_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "vide.txt"
            fichier.write_text("   \n", encoding="utf-8")

            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                with self.assertRaises(ValueError):
                    load_profil()

    @mock.patch.dict(os.environ, {ENV_PROFIL: AUTRE_PROFIL}, clear=True)
    def test_a_profile_given_as_a_line_carries_nothing_else(self):
        """Une variable d'environnement est une ligne, pas un document : ni stack ni adresse."""
        profil = load_profil()

        self.assertTrue(profil.stack.vide)
        self.assertEqual((), profil.emails)


class DocumentTests(unittest.TestCase):
    """Le document JSON : un profil, une stack, un destinataire, lus d'un seul tenant."""

    def test_the_three_keys_are_read_at_once(self):
        profil = charge(
            {
                CLE_PROFIL: AUTRE_PROFIL,
                CLE_STACK: ["Traefik"],
                CLE_EMAIL: "moi@example.com",
            }
        )

        self.assertEqual(AUTRE_PROFIL, profil.texte)
        self.assertEqual(("Traefik",), profil.stack.concernes("Vulnérabilité dans Traefik"))
        self.assertEqual(("moi@example.com",), profil.emails)

    def test_the_text_is_trimmed_like_a_plain_file(self):
        self.assertEqual(AUTRE_PROFIL, charge({CLE_PROFIL: f"\n  {AUTRE_PROFIL}\n"}).texte)

    def test_other_keys_are_ignored(self):
        """De quoi annoter le document sans que la note entre dans le prompt."""
        profil = charge({"_note": "tenu hors git", CLE_PROFIL: AUTRE_PROFIL})

        self.assertEqual(AUTRE_PROFIL, profil.texte)

    def test_a_text_file_is_never_parsed(self):
        """L'accolade ouvrante décide, pas l'extension : un profil en clair reste du texte."""
        self.assertEqual(AUTRE_PROFIL, charge(AUTRE_PROFIL).texte)

    def test_a_broken_json_raises_instead_of_passing_for_text(self):
        """Sinon la ponctuation du fichier deviendrait le critère de pertinence du jour."""
        with self.assertRaises(ValueError):
            charge('{"profil": "profil tronqué')

    def test_a_json_without_the_profil_key_raises(self):
        with self.assertRaises(ValueError):
            charge({"metier": AUTRE_PROFIL})

    def test_a_json_whose_profil_key_is_empty_raises(self):
        with self.assertRaises(ValueError):
            charge({CLE_PROFIL: "   "})

    def test_a_json_whose_profil_key_is_not_a_string_raises(self):
        with self.assertRaises(ValueError):
            charge({CLE_PROFIL: ["un", "profil"]})


class StackDuDocumentTests(unittest.TestCase):
    """La clé `stack` du document. Le format d'une entrée, lui, est dans `test_certfr`."""

    def _stack(self, entrees):
        return charge({CLE_PROFIL: AUTRE_PROFIL, CLE_STACK: entrees}).stack

    def test_a_missing_key_leaves_an_empty_stack(self):
        """L'état de qui vient d'installer l'outil : le digest le dit en toutes lettres."""
        self.assertTrue(charge({CLE_PROFIL: AUTRE_PROFIL}).stack.vide)

    def test_the_declared_components_are_matched(self):
        stack = self._stack(["Traefik", {"nom": "Keycloak", "alias": ["RH-SSO"]}])

        self.assertEqual(2, len(stack))
        self.assertEqual(("Traefik",), stack.concernes("Multiples vulnérabilités dans Traefik"))
        self.assertEqual(("Keycloak",), stack.concernes("Vulnérabilité dans RH-SSO"))

    def test_a_faulty_entry_fails_the_load(self):
        """La stack est lue avec le profil : elle échoue au lancement, pas au troisième avis.

        Sous `ValueError`, la seule exception d'un document refusé, mais l'erreur de la
        stack reste la cause : c'est elle qui dit quelle entrée est fautive.
        """
        with self.assertRaises(ValueError) as leve:
            self._stack([{"alias": ["RH-SSO"]}])
        self.assertIsInstance(leve.exception.__cause__, StackError)


class EmailTests(unittest.TestCase):
    """La clé `email` : à qui la lettre est adressée, déclaré avec le reste du personnel."""

    def _emails(self, valeur):
        return charge({CLE_PROFIL: AUTRE_PROFIL, CLE_EMAIL: valeur}).emails

    def test_one_address_is_read(self):
        self.assertEqual(("moi@example.com",), self._emails("moi@example.com"))

    def test_several_addresses_are_read(self):
        self.assertEqual(
            ("moi@example.com", "autre@example.com"),
            self._emails(["moi@example.com", "autre@example.com"]),
        )

    def test_a_missing_key_sends_to_nobody(self):
        """Comme `SMTP_TO` absente auparavant : l'envoi est sauté, sans erreur."""
        self.assertEqual((), charge({CLE_PROFIL: AUTRE_PROFIL}).emails)

    def test_something_that_is_not_an_address_raises(self):
        """La faute qui arrive vraiment : une clé remplie avec autre chose qu'une adresse."""
        with self.assertRaises(ValueError):
            self._emails("Adrien")

    def test_an_empty_list_raises(self):
        with self.assertRaises(ValueError):
            self._emails([])


class PrenomTests(unittest.TestCase):
    """La clé `prenom` : par quel nom l'audio de journée ouvre. Facultative, mais pas
    permissive, une salutation qui se trompe ne se voit qu'à l'écoute, un matin."""

    def _prenom(self, valeur):
        return charge({CLE_PROFIL: AUTRE_PROFIL, CLE_PRENOM: valeur}).prenom

    def test_the_first_name_is_read(self):
        self.assertEqual("Adrien", self._prenom("  Adrien  "))

    def test_a_missing_key_greets_nobody_by_name(self):
        self.assertEqual("", charge({CLE_PROFIL: AUTRE_PROFIL}).prenom)

    def test_an_empty_key_greets_nobody_by_name(self):
        self.assertEqual("", self._prenom("   "))

    def test_something_that_is_not_a_name_raises(self):
        with self.assertRaises(ValueError):
            self._prenom(["Adrien"])

    def test_a_plain_text_document_declares_no_first_name(self):
        """Un profil en texte brut ne porte que lui : ni stack, ni adresse, ni prénom."""
        self.assertEqual("", charge(AUTRE_PROFIL).prenom)


class SecuriteTests(unittest.TestCase):
    """La clé `securite` : le détail que les vulnérabilités méritent pour cette personne.

    Une valeur inconnue lève au lancement : servie au défaut, elle rendrait les plages de
    versions à qui avait justement demandé de ne plus les entendre.
    """

    def _securite(self, valeur):
        return charge({CLE_PROFIL: AUTRE_PROFIL, CLE_SECURITE: valeur}).securite

    def test_a_missing_key_means_exploitant(self):
        self.assertIs(Securite.EXPLOITANT, charge({CLE_PROFIL: AUTRE_PROFIL}).securite)
        self.assertIs(Securite.EXPLOITANT, charge(AUTRE_PROFIL).securite)

    def test_each_declared_value_is_read(self):
        for securite in Securite:
            with self.subTest(securite=securite):
                self.assertIs(securite, self._securite(securite.value))

    def test_an_unknown_value_is_refused(self):
        """Pas de casse corrigée en silence : le site relirait autre chose que la tournée."""
        for valeur in ("expert", "Decideur"):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError) as leve:
                    profil_depuis_dict({CLE_PROFIL: "x", CLE_SECURITE: valeur}, origine="bea")
                self.assertIn("bea", str(leve.exception))
                self.assertIn(CLE_SECURITE, str(leve.exception))

    def test_something_that_is_not_a_text_is_refused(self):
        for valeur in (3, ["curieux"]):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError):
                    self._securite(valeur)


def article_du_flux(flux, categorie="Tech"):
    return Article(
        item_id="item-1",
        category=categorie,
        title="Épisode 512",
        url="https://example.com/episode",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title=flux,
        content_text="",
    )


class FluxExclusTests(unittest.TestCase):
    """La clé `flux_exclus` : les flux qui ne se résument pas, retirés du scoring.

    L'appariement porte sur le titre du flux, à l'égalité près de la casse et des accents :
    une inclusion écarterait en silence un flux voisin, et ce qu'on ne reçoit plus ne se
    remarque qu'à son absence.
    """

    def _exclus(self, valeur):
        return charge({CLE_PROFIL: AUTRE_PROFIL, CLE_FLUX_EXCLUS: valeur}).flux_exclus

    def test_the_declared_titles_are_read_and_kept_as_written(self):
        exclus = self._exclus([" NoLimitSecu ", "FreshRSS releases"])

        self.assertEqual(("NoLimitSecu", "FreshRSS releases"), exclus.titres)
        self.assertEqual(["NoLimitSecu", "FreshRSS releases"], exclus.en_document())

    def test_matching_ignores_case_and_accents(self):
        exclus = self._exclus(["NoLimitSecu", "Journal des Évolutions"])

        for flux in ("nolimitsecu", "NOLIMITSECU", "  NoLimitSecu ", "journal des evolutions"):
            with self.subTest(flux=flux):
                self.assertTrue(exclus.exclut(article_du_flux(flux)))

    def test_matching_reads_the_feed_title_not_the_category(self):
        exclus = self._exclus(["NoLimitSecu"])

        self.assertFalse(exclus.exclut(article_du_flux("Le Monde Informatique", categorie="NoLimitSecu")))
        self.assertTrue(exclus.exclut(article_du_flux("NoLimitSecu", categorie="Cybersécurité")))

    def test_a_feed_title_merely_containing_an_excluded_one_is_kept(self):
        exclus = self._exclus(["Go"])

        self.assertFalse(exclus.exclut(article_du_flux("Google Cloud Blog")))
        self.assertFalse(exclus.exclut(article_du_flux("The Go Blog")))
        self.assertTrue(exclus.exclut(article_du_flux("go")))

    def test_an_absent_or_empty_list_excludes_nothing(self):
        for exclus in (charge({CLE_PROFIL: AUTRE_PROFIL}).flux_exclus, self._exclus([]),
                       charge(AUTRE_PROFIL).flux_exclus, FluxExclus()):
            with self.subTest(exclus=exclus.titres):
                self.assertFalse(exclus)
                self.assertFalse(exclus.exclut(article_du_flux("NoLimitSecu")))
                self.assertEqual([], exclus.en_document())

    def test_two_lists_excluding_the_same_feeds_are_equal_and_show_their_titles(self):
        """`AppConfig` est une dataclass : sans égalité, deux configs identiques différeraient."""
        self.assertEqual(FluxExclus(["NoLimitSecu"]), FluxExclus(["nolimitsecu "]))
        self.assertEqual(hash(FluxExclus(["NoLimitSecu"])), hash(FluxExclus(["NOLIMITSECU"])))
        self.assertNotEqual(FluxExclus(["NoLimitSecu"]), FluxExclus(["FreshRSS releases"]))
        self.assertEqual(FluxExclus(), FluxExclus([]))
        self.assertEqual("FluxExclus(['NoLimitSecu'])", repr(FluxExclus(["NoLimitSecu"])))

    def test_a_malformed_list_fails_at_startup(self):
        for valeur in ("NoLimitSecu", {"NoLimitSecu": True}, ["NoLimitSecu", ""], ["  "], [3],
                       ["NoLimitSecu", "nolimitsecu"]):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError) as leve:
                    profil_depuis_dict({CLE_PROFIL: "x", CLE_FLUX_EXCLUS: valeur}, origine="bea")
                self.assertIn("bea", str(leve.exception))
                self.assertIn(CLE_FLUX_EXCLUS, str(leve.exception))


class ChampInvalideTests(unittest.TestCase):
    """Le refus nomme la clé fautive : le site l'affiche sous le champ concerné.

    Il reste une `ValueError` au message inchangé : la tournée et la CLI ne voient rien.
    """

    def test_each_faulty_key_names_its_field(self):
        catalogue = Catalogue([
            CategorieCatalogue("Tech", "Tech.", ["cto"]),
            CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["adrien"]),
        ])
        fautes = {
            CLE_PROFIL: {CLE_PROFIL: "  "},
            CLE_STACK: {CLE_STACK: "Traefik"},
            CLE_AXES: {CLE_AXES: [{"slug": "a", "libelle": "A", "description": "a"}]},
            CLE_ID: {CLE_ID: "PAS-UN-UUID"},
            CLE_EMAIL: {CLE_EMAIL: "pas-une-adresse"},
            CLE_PRENOM: {CLE_PRENOM: 3},
            CLE_SECURITE: {CLE_SECURITE: "expert"},
            CLE_FLUX_EXCLUS: {CLE_FLUX_EXCLUS: [""]},
            CLE_CATEGORIES: {CLE_CATEGORIES: []},
        }
        for champ, faute in fautes.items():
            with self.subTest(champ=champ):
                with self.assertRaises(ChampInvalide) as leve:
                    profil_depuis_dict({CLE_PROFIL: "x", **faute}, origine="bea")
                self.assertEqual(champ, leve.exception.champ)
                self.assertIsInstance(leve.exception, ValueError)
                self.assertIn("bea", str(leve.exception))

        # Refusée par le catalogue, inconnue ou privée d'un autre : même champ.
        for categorie in ("Inconnue", "Veille marché"):
            with self.subTest(categorie=categorie):
                with self.assertRaises(ChampInvalide) as leve:
                    profil_depuis_dict(
                        {CLE_PROFIL: "x", CLE_CATEGORIES: [categorie]}, "bea", catalogue, "bea"
                    )
                self.assertEqual(CLE_CATEGORIES, leve.exception.champ)
                self.assertIn("inconnue du catalogue", str(leve.exception))


class InjectedProfileTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_both_prompts_carry_the_injected_profile(self):
        self.assertIn(AUTRE_PROFIL, scoring_system(AUTRE_PROFIL))
        self.assertIn(AUTRE_PROFIL, article_system(AUTRE_PROFIL))
        self.assertNotIn(DEFAULT_PROFIL, scoring_system(AUTRE_PROFIL))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_the_scoring_prompt_keeps_its_json_braces(self):
        """Le prompt est concaténé, pas formaté : ses accolades ne sont pas des champs."""
        self.assertIn('{"resultats": [{"id": "...", "score": 0', scoring_system(AUTRE_PROFIL))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_a_profile_containing_braces_is_accepted(self):
        profil = 'Développeur : je suis {"json"} et les accolades {} de près.'

        self.assertIn(profil, scoring_system(profil))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_changing_the_profile_invalidates_the_scoring_cache(self):
        """Sinon des scores calculés contre l'ancien profil survivraient au changement."""
        self.assertNotEqual(empreinte(), empreinte(AUTRE_PROFIL))
        # Même profil, même empreinte : relancer la journée ne repaie rien.
        self.assertEqual(empreinte(AUTRE_PROFIL), empreinte(AUTRE_PROFIL))


class AxesDeVeilleAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.axes = Axes.declares([
            {"slug": "qualite", "libelle": "Qualité", "description": "tests et fiabilité"},
            {"slug": "livraison", "libelle": "Livraison", "description": "outillage et déploiement"},
            {"slug": "experience", "libelle": "Expérience", "description": "usage et conception"},
        ])

    def test_custom_axes_are_in_the_prompt_not_the_defaults(self):
        prompt = scoring_system(AUTRE_PROFIL, self.axes)
        for slug in ("qualite", "livraison", "experience"):
            self.assertIn(slug, prompt)
        self.assertNotIn("exactement une valeur parmi reglementaire, cyber, marche, stack, autre", prompt)

    def test_a_thematique_outside_axes_falls_back_to_the_last_one(self):
        from rssresume.llm.processing import read_scores
        lot = [{"id": "a", "title": "Article", "summary": "Résumé"}]
        notes = read_scores('{"resultats":[{"id":"a","score":8,"thematique":"cyber","angle":"impact"}]}', lot, self.axes)
        self.assertEqual("experience", notes[0]["thematique"])

    def test_a_declared_theme_slug_is_a_valid_axe(self):
        """Le slug d'un axe déclaré est retenu tel quel, sans repli sur « autre »."""
        self.assertTrue(self.axes.contient("qualite"))

    def test_absent_key_keeps_prompt_and_validation_unchanged(self):
        axes = Axes.declares(None)
        prompt = scoring_system(AUTRE_PROFIL, axes)
        self.assertIn("exactement une valeur parmi reglementaire, cyber, marche, stack, autre", prompt)
        self.assertEqual("autre", axes.rabattre("inconnu"))

    def test_slug_and_axis_count_are_validated_with_a_clear_error(self):
        for axes_fautifs in (
            [{"slug": "ok", "libelle": "OK", "description": "valide"},
             {"slug": "deux", "libelle": "Deux", "description": "valide"}],
            [{"slug": "Mauvais!", "libelle": "Mauvais", "description": "valide"},
             {"slug": "deux", "libelle": "Deux", "description": "valide"},
             {"slug": "trois", "libelle": "Trois", "description": "valide"}],
        ):
            with self.subTest(axes=axes_fautifs):
                with self.assertRaises(ValueError):
                    profil_depuis_dict({CLE_PROFIL: "Profil", CLE_AXES: axes_fautifs})


if __name__ == "__main__":
    unittest.main()
