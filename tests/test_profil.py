"""Chargement du document de profil, et effets de son injection.

Un seul fichier porte tout ce qui est personnel : le critère de pertinence, la stack
surveillée, le destinataire du digest. Ces tests protègent les deux extrémités — que le
document soit lu en entier, et qu'un document fautif fasse échouer le lancement plutôt
que de laisser noter une journée contre un critère qui n'est pas celui qu'on croit.
"""

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
from rssresume.profil import (
    CLE_EMAIL,
    CLE_PRENOM,
    CLE_PROFIL,
    CLE_SECURITE,
    CLE_STACK,
    DEFAULT_PROFIL,
    ENV_PROFIL,
    ENV_PROFIL_FILE,
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
    permissive — une salutation qui se trompe ne se voit qu'à l'écoute, un matin."""

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

    def test_cache_reloads_a_declared_theme_slug(self):
        from rssresume.external.freshrss import Etiquettes
        etiquettes = Etiquettes("adrien")
        self.assertEqual("qualite", etiquettes.theme_de(("adrien-theme-qualite",)))
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
