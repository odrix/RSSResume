"""La base de profils : ce qu'elle accepte, ce qu'elle garde, et qui la lit.

Ce que ces tests protègent :

- la base refuse ce que la tournée refuserait — mêmes messages que `profil_depuis_dict` ;
- un nom n'est pris qu'une fois, un identifiant ne change jamais ;
- la tournée sert les profils de la base sans rien savoir d'elle ;
- la base exclut toute autre source de profils, au lancement ;
- l'import se rejoue sans rien réécrire, et garde les identifiants des fichiers.
"""

import datetime
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from rssresume.annuaire_sqlite import AnnuaireSqlite, ProfilDejaPris, ProfilInconnu
from rssresume.api import __main__ as api_main
from rssresume.api.importation import Importateur
from rssresume.categories import Catalogue
from rssresume.desabonnement import OBJET_DESABONNEMENT, Desabonnement, Signataire
from rssresume.digest import DigestService
from rssresume.profil import (
    ENV_PROFIL,
    ENV_PROFIL_FILE,
    ENV_PROFILES_DB,
    ENV_PROFILES_DIR,
    Annuaire,
    Securite,
    id_valide,
    nouvel_id,
)
from rssresume.retours import Avis, Retour
from rssresume.summaries import SummaryGenerator
from rssresume.tournee import Tournee
from tests import test_multiprofil
from tests.support import FakeAudioGenerator, FakeEmailSender, make_config

JOUR = test_multiprofil.JOUR


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self._tmp.name)
        self.annuaire = AnnuaireSqlite(self.tmpdir / "data" / "profils.sqlite3")

    def tearDown(self):
        self._tmp.cleanup()


class AnnuaireSqliteTests(Base):
    def test_a_profile_is_written_normalised_and_read_back(self):
        fiche = self.annuaire.creer(
            "bea", {"profil": " Veille ", "stack": ["Traefik"], "email": "b@example.com", "prenom": "Bea", "autre": 1}
        )

        self.assertTrue(id_valide(fiche.id))
        relue = self.annuaire.fiche("bea")
        self.assertEqual(
            {"id": fiche.id, "username": "bea", "profil": "Veille", "stack": ["Traefik"],
             "email": ["b@example.com"], "prenom": "Bea", "securite": "exploitant",
             "modifie_le": relue.modifie_le},
            relue.complet_json(),
        )
        self.assertEqual("Veille", self.annuaire.profil("bea").texte)
        self.assertEqual(["bea"], self.annuaire.usernames())

    def test_the_normalised_document_keeps_the_security_regime(self):
        """Gardée comme le prénom : une clé retirée à l'écriture serait perdue au matin."""
        declare = self.annuaire.creer("bea", {"profil": "B", "securite": "decideur"})
        absent = self.annuaire.creer("zoe", {"profil": "Z"})

        self.assertEqual("decideur", declare.document["securite"])
        # Écrite même absente de la saisie : le document stocké dit ce qui sera servi.
        self.assertEqual("exploitant", absent.document["securite"])
        self.assertEqual(Securite.DECIDEUR, self.annuaire.profil("bea").securite)
        self.assertEqual("decideur", self.annuaire.fiche("bea").complet_json()["securite"])

    def test_the_names_are_sorted(self):
        for nom in ("zoe", "adrien", "bea"):
            self.annuaire.creer(nom, {"profil": nom})
        self.assertEqual(["adrien", "bea", "zoe"], self.annuaire.usernames())

    def test_a_name_is_taken_only_once(self):
        self.annuaire.creer("bea", {"profil": "B"})
        with self.assertRaises(ProfilDejaPris):
            self.annuaire.creer("bea", {"profil": "B2"})

    def test_an_id_is_taken_only_once(self):
        id = nouvel_id()
        self.annuaire.creer("bea", {"profil": "B"}, id=id)
        with self.assertRaises(ProfilDejaPris):
            self.annuaire.creer("zoe", {"profil": "Z"}, id=id)

    def test_faulty_documents_and_names_are_refused_with_the_shared_message(self):
        for nom, document in (
            ("bea", {"profil": ""}),
            ("bea", {"profil": "x", "email": "pas-une-adresse"}),
            ("bea", {"profil": "x", "stack": "Traefik"}),
            ("bea", ["pas un objet"]),
            ("Bea", {"profil": "x"}),
        ):
            with self.assertRaises(ValueError):
                self.annuaire.creer(nom, document)
        self.assertEqual([], self.annuaire.usernames())

    def test_an_update_keeps_the_id_and_the_creation_date(self):
        avant = self.annuaire.creer("bea", {"profil": "B"})

        apres = self.annuaire.modifier("bea", {"profil": "B2", "email": ["b@example.com"]})

        self.assertEqual(avant.id, apres.id)
        self.assertEqual(avant.cree_le, apres.cree_le)
        self.assertEqual("B2", self.annuaire.profil("bea").texte)

    def test_unknown_profiles(self):
        with self.assertRaises(ProfilInconnu):
            self.annuaire.fiche("bea")
        with self.assertRaises(ProfilInconnu):
            self.annuaire.modifier("bea", {"profil": "B"})
        with self.assertRaises(ProfilInconnu):
            self.annuaire.supprimer("bea")
        with self.assertRaises(ValueError):
            self.annuaire.cibles("bea")

    def test_a_deleted_profile_leaves_the_tour(self):
        self.annuaire.creer("bea", {"profil": "B"})
        self.annuaire.supprimer("bea")
        self.assertEqual([], self.annuaire.usernames())

    def test_the_database_is_in_wal_mode(self):
        """Deux processus — la tournée, l'API — lisent et écrivent ensemble."""
        with self.annuaire._connexion() as connexion:
            self.assertEqual("wal", connexion.execute("PRAGMA journal_mode").fetchone()[0])

    def test_a_document_edited_by_hand_is_validated_again_on_reading(self):
        self.annuaire.creer("bea", {"profil": "B"})
        with self.annuaire._connexion() as connexion:
            connexion.execute("UPDATE profils SET document = ?", (json.dumps({"profil": ""}),))
        with self.assertRaises(ValueError):
            self.annuaire.profil("bea")

    def test_an_empty_axes_list_removes_the_custom_axes(self):
        fiche = self.annuaire.creer("bea", {"profil": "B", "axes": []})

        self.assertNotIn("axes", fiche.document)
        self.assertFalse(self.annuaire.profil("bea").axes.sont_declares)

    def test_an_empty_categories_list_removes_the_subscription(self):
        fiche = self.annuaire.creer("bea", {"profil": "B", "categories": []})

        self.assertNotIn("categories", fiche.document)
        self.assertIsNone(self.annuaire.profil("bea").categories)

    def test_excluded_feeds_survive_writing_and_reading(self):
        """Une clé que `document_normalise` ne connaîtrait pas disparaîtrait en silence."""
        fiche = self.annuaire.creer("bea", {"profil": "B", "flux_exclus": [" NoLimitSecu ", "FreshRSS releases"]})

        self.assertEqual(["NoLimitSecu", "FreshRSS releases"], fiche.document["flux_exclus"])
        self.assertEqual(
            ("NoLimitSecu", "FreshRSS releases"), self.annuaire.profil("bea").flux_exclus.titres
        )
        self.assertEqual(
            ["NoLimitSecu", "FreshRSS releases"], self.annuaire.fiche("bea").complet_json()["flux_exclus"]
        )

    def test_an_empty_excluded_feeds_list_is_omitted_from_the_document(self):
        fiche = self.annuaire.creer("bea", {"profil": "B", "flux_exclus": []})

        self.assertNotIn("flux_exclus", fiche.document)
        self.assertNotIn("flux_exclus", self.annuaire.fiche("bea").complet_json())
        self.assertFalse(self.annuaire.profil("bea").flux_exclus)


class DesabonnerTests(Base):
    """Le lien de désabonnement vide les destinataires, une fois, et seulement les siens."""

    def setUp(self):
        super().setUp()
        self.service = Desabonnement(Signataire("k" * 48, OBJET_DESABONNEMENT))
        self.fiche = self.annuaire.creer(
            "bea", {"profil": "B", "stack": ["Traefik"], "email": ["b@example.com", "c@example.com"]}
        )

    def _demande(self, emails=("b@example.com", "c@example.com"), id=None):
        return self.service.lire(self.service.jeton(id or self.fiche.id, list(emails)))

    def test_the_recipients_are_emptied_and_the_document_stays_normalised(self):
        fiche = self.annuaire.desabonner(self._demande())

        self.assertEqual("bea", fiche.username)
        relue = self.annuaire.fiche("bea")
        # Comme `document_normalise` l'écrirait sans destinataire : la clé est omise.
        self.assertNotIn("email", relue.document)
        self.assertEqual(["Traefik"], relue.document["stack"])
        self.assertEqual((), tuple(self.annuaire.profil("bea").emails))
        self.assertGreaterEqual(relue.modifie_le, self.fiche.modifie_le)

    def test_the_link_serves_only_once(self):
        demande = self._demande()

        self.assertIsNotNone(self.annuaire.desabonner(demande))
        self.assertIsNone(self.annuaire.desabonner(demande))

    def test_a_link_of_a_letter_sent_to_a_smaller_list_still_works(self):
        """La liste a grandi depuis l'envoi : le lien des lettres déjà parties vaut encore."""
        self.assertIsNotNone(self.annuaire.desabonner(self._demande(emails=["B@example.com"])))
        self.assertNotIn("email", self.annuaire.fiche("bea").document)

    def test_a_link_for_none_of_the_current_recipients_changes_nothing(self):
        """Aucune adresse de la lettre ne reçoit plus le résumé : le lien ne désigne plus personne."""
        self.assertIsNone(self.annuaire.desabonner(self._demande(emails=["z@example.com"])))
        self.assertEqual(["b@example.com", "c@example.com"], self.annuaire.fiche("bea").document["email"])

    def test_an_unknown_profile_changes_nothing(self):
        self.assertIsNone(self.annuaire.desabonner(self._demande(id=nouvel_id())))

    def test_a_single_address_stored_as_a_string_is_read_like_the_worker_does(self):
        """Une base se modifie aussi à la main : `"email": "a@x.fr"` reste une adresse."""
        document = {**self.fiche.document, "email": "a@x.fr"}
        with self.annuaire._connexion() as connexion:
            connexion.execute(
                "UPDATE profils SET document = ? WHERE id = ?", (json.dumps(document), self.fiche.id)
            )
        # Le lien tel que le travailleur le signe : sur les adresses que le profil lu donne.
        emails = self.annuaire.profil("bea").emails

        fiche = self.annuaire.desabonner(self._demande(emails=emails))

        self.assertEqual(("a@x.fr",), tuple(emails))
        self.assertIsNotNone(fiche)
        self.assertNotIn("email", self.annuaire.fiche("bea").document)


class RetoursTests(Base):
    """Un vote par profil et par journée : le second remplace le premier."""

    JOUR = datetime.date(2026, 11, 22)

    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B"})

    def _retour(self, avis=Avis.UTILE, commentaire="", jour=None, profil_id=None):
        return Retour(profil_id or self.fiche.id, jour or self.JOUR, avis, commentaire)

    def _lignes(self):
        with self.annuaire._connexion() as connexion:
            return connexion.execute("SELECT profil_id, jour, avis, commentaire FROM retours").fetchall()

    def test_a_second_vote_on_the_same_day_replaces_the_first(self):
        self.annuaire.enregistrer_retour(self._retour(Avis.UTILE, "Bien."))
        self.annuaire.enregistrer_retour(self._retour(Avis.PAS_UTILE, "Finalement non."))

        self.assertEqual([(self.fiche.id, "2026-11-22", "pas_utile", "Finalement non.")], self._lignes())
        relu = self.annuaire.retour(self.fiche.id, self.JOUR)
        self.assertEqual((Avis.PAS_UTILE, "Finalement non.", "bea"), (relu.avis, relu.commentaire, relu.username))

    def test_another_day_is_another_vote(self):
        self.annuaire.enregistrer_retour(self._retour())
        self.annuaire.enregistrer_retour(self._retour(jour=self.JOUR - datetime.timedelta(days=1)))

        self.assertEqual(2, len(self._lignes()))

    def test_the_database_dates_the_vote(self):
        enregistre = self.annuaire.enregistrer_retour(self._retour())

        self.assertIsNotNone(enregistre.vote_le)
        self.assertEqual(enregistre.vote_le, self.annuaire.retour(self.fiche.id, self.JOUR).vote_le)
        self.assertIsNone(self.annuaire.retour(self.fiche.id, self.JOUR - datetime.timedelta(days=1)))

    def test_the_list_is_most_recent_first_bounded_and_survives_a_deleted_profile(self):
        autre = self.annuaire.creer("cle", {"profil": "C"})
        for rang, (profil_id, horodatage) in enumerate(
            ((self.fiche.id, "2026-11-20T07:00:00+00:00"), (autre.id, "2026-11-22T07:00:00+00:00"),
             (self.fiche.id, "2026-11-21T07:00:00+00:00"))
        ):
            jour = self.JOUR - datetime.timedelta(days=rang)
            with mock.patch("rssresume.annuaire_sqlite._maintenant", return_value=horodatage):
                self.annuaire.enregistrer_retour(self._retour(jour=jour, profil_id=profil_id))
        self.annuaire.supprimer("cle")

        retours = self.annuaire.retours(10)

        self.assertEqual(
            ["2026-11-22T07:00:00+00:00", "2026-11-21T07:00:00+00:00", "2026-11-20T07:00:00+00:00"],
            [retour.vote_le for retour in retours],
        )
        # Le profil a disparu, son retour reste, sans nom.
        self.assertEqual([None, "bea", "bea"], [retour.username for retour in retours])
        self.assertEqual(2, len(self.annuaire.retours(2)))

    def test_the_table_is_created_on_an_existing_database(self):
        """Pas de migrations : une base d'avant les retours gagne sa table à la première ouverture."""
        chemin = self.tmpdir / "ancienne.sqlite3"
        with sqlite3.connect(chemin) as connexion:
            connexion.execute(
                "CREATE TABLE profils (id TEXT PRIMARY KEY NOT NULL, username TEXT NOT NULL UNIQUE, "
                "document TEXT NOT NULL, cree_le TEXT NOT NULL, modifie_le TEXT NOT NULL)"
            )
        connexion.close()

        annuaire = AnnuaireSqlite(chemin)
        annuaire.enregistrer_retour(self._retour())

        self.assertEqual(Avis.UTILE, annuaire.retour(self.fiche.id, self.JOUR).avis)


class DepuisEnvTests(Base):
    def test_the_database_variable_selects_the_database(self):
        chemin = str(self.tmpdir / "profils.sqlite3")
        with mock.patch.dict(os.environ, {ENV_PROFILES_DB: chemin}, clear=True):
            self.assertIsInstance(Annuaire.depuis_env(), AnnuaireSqlite)

    def test_the_database_excludes_every_other_source(self):
        for autre in (ENV_PROFILES_DIR, ENV_PROFIL_FILE, ENV_PROFIL):
            env = {ENV_PROFILES_DB: str(self.tmpdir / "p.sqlite3"), autre: "x"}
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError) as leve:
                    Annuaire.depuis_env()
            self.assertIn(autre, str(leve.exception))
            self.assertIn(ENV_PROFILES_DB, str(leve.exception))


class TourneeSurBaseTests(Base):
    """La boucle quotidienne sert la base comme elle servait le dossier."""

    def test_the_tour_serves_the_database_profiles_under_their_id(self):
        bea = self.annuaire.creer("bea", {"profil": "B"})
        zoe = self.annuaire.creer("zoe", {"profil": "Z"})
        self.annuaire.remplacer_catalogue(test_multiprofil.catalogue_public("Tech", "News"))
        client = test_multiprofil.FreshRSSQuiOublieLesLus(
            {"Tech": [test_multiprofil.article("item-1")], "News": [test_multiprofil.article("item-2")]}
        )
        vus = []

        def assembleur(config, freshrss):
            vus.append(config.username)
            return DigestService(
                config=config,
                freshrss_client=freshrss.pour(config.username),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

        tournee = Tournee(make_config(self.tmpdir / "output"), self.annuaire, client, assembleur)
        echecs = tournee.run(JOUR, send_email=False)

        self.assertEqual([], echecs)
        self.assertEqual(["bea", "zoe"], sorted(vus))
        self.assertEqual(1, client.appels_marquage)
        for fiche in (bea, zoe):
            self.assertTrue((self.tmpdir / "output" / fiche.id / JOUR.isoformat()).is_dir())


class ImportTests(Base):
    def _dossier(self, documents):
        dossier = self.tmpdir / "profils"
        dossier.mkdir()
        for nom, contenu in documents.items():
            texte = contenu if isinstance(contenu, str) else json.dumps(contenu)
            (dossier / nom).write_text(texte, encoding="utf-8")
        return dossier

    def test_the_import_keeps_ids_is_idempotent_and_leaves_the_files(self):
        id_bea = nouvel_id()
        dossier = self._dossier({
            "bea.json": {"id": id_bea, "profil": "B", "email": "b@example.com"},
            "zoe.json": {"profil": "Z"},
            "texte.json": "Un profil écrit en clair.",
            "README.md": "pas un profil",
        })
        avant = {f.name: f.read_bytes() for f in dossier.iterdir()}

        premier = Importateur(self.annuaire).importer(dossier)
        id_zoe = self.annuaire.fiche("zoe").id
        second = Importateur(self.annuaire).importer(dossier)

        self.assertEqual(["bea", "texte", "zoe"], premier.importes)
        self.assertEqual([], premier.erreurs)
        self.assertEqual([], second.importes)
        self.assertEqual(["bea", "texte", "zoe"], second.deja_la)
        self.assertEqual(id_bea, self.annuaire.fiche("bea").id)
        self.assertEqual(id_zoe, self.annuaire.fiche("zoe").id)
        self.assertEqual("Un profil écrit en clair.", self.annuaire.profil("texte").texte)
        self.assertEqual(avant, {f.name: f.read_bytes() for f in dossier.iterdir()})

    def test_the_import_never_overwrites_what_the_site_edited(self):
        dossier = self._dossier({"bea.json": {"profil": "B"}})
        Importateur(self.annuaire).importer(dossier)
        self.annuaire.modifier("bea", {"profil": "édité sur le site"})

        Importateur(self.annuaire).importer(dossier)

        self.assertEqual("édité sur le site", self.annuaire.profil("bea").texte)

    def test_faulty_files_are_reported_and_the_others_imported(self):
        dossier = self._dossier({
            "Jean Paul.json": {"profil": "J"},
            "casse.json": '{"profil": ',
            "vide.json": {"profil": ""},
            "bea.json": {"profil": "B"},
        })

        bilan = Importateur(self.annuaire).importer(dossier)

        self.assertEqual(["bea"], bilan.importes)
        self.assertEqual(3, len(bilan.erreurs))
        self.assertTrue(bilan.en_echec)

    def test_an_id_already_used_by_another_name_is_a_conflict(self):
        id = nouvel_id()
        self.annuaire.creer("bea", {"profil": "B"}, id=id)
        dossier = self._dossier({"zoe.json": {"id": id, "profil": "Z"}})

        bilan = Importateur(self.annuaire).importer(dossier)

        self.assertEqual([], bilan.importes)
        self.assertEqual(1, len(bilan.erreurs))

    def test_the_command_line_imports_into_the_declared_database(self):
        dossier = self._dossier({"bea.json": {"profil": "B"}, "casse.json": "{"})
        env = {ENV_PROFILES_DB: str(self.annuaire.chemin)}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(1, api_main.main(["importer", str(dossier)]))
            self.assertEqual(["bea"], self.annuaire.usernames())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(2, api_main.main(["importer", str(dossier)]))

    def test_a_single_file_is_imported_under_its_name(self):
        fichier = self.tmpdir / "adrien.json"
        fichier.write_text(json.dumps({"profil": "A"}), encoding="utf-8")

        bilan = Importateur(self.annuaire).importer(fichier)

        self.assertEqual(["adrien"], bilan.importes)


class CatalogueBaseTests(Base):
    """Le catalogue en base : remplacé en entier, revalidé à chaque lecture."""

    PUBLIQUE = {"description": "Tech.", "metiers": ["cto"], "visibilite": "publique"}
    PRIVEE = {"description": "Veille.", "metiers": [], "visibilite": "privee", "proprietaires": ["bea"]}

    def _fichier(self, document, nom="categories.json"):
        fichier = self.tmpdir / nom
        fichier.write_text(
            document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
        )
        return fichier

    def test_an_empty_table_is_an_open_catalogue(self):
        self.assertTrue(self.annuaire.catalogue().ouvert)

    def test_without_catalogue_two_database_profiles_are_told_to_import_it(self):
        """En base, le remède est la seule commande d'import : pas de migration à proposer."""
        self.annuaire.creer("bea", {"profil": "B"})
        self.annuaire.creer("zoe", {"profil": "Z"})
        client = test_multiprofil.FreshRSSQuiOublieLesLus({"Tech": []})
        tournee = Tournee(make_config(self.tmpdir / "output"), self.annuaire, client, None)

        with self.assertRaises(ValueError) as leve:
            tournee.run(JOUR, send_email=False)

        self.assertIn("importer-catalogue", str(leve.exception))
        self.assertNotIn("importer <dossier>", str(leve.exception))

    def test_the_catalogue_import_replaces_the_table_and_refuses_a_faulty_document_without_writing(self):
        self.annuaire.remplacer_catalogue(
            Catalogue.depuis_document({"Tech": self.PUBLIQUE, "Ancienne": self.PUBLIQUE}, "test")
        )
        self.annuaire.remplacer_catalogue(
            Catalogue.depuis_document({"Tech": self.PUBLIQUE, "Veille": self.PRIVEE}, "test")
        )

        relu = self.annuaire.catalogue()
        self.assertEqual(["Tech", "Veille"], sorted(e.libelle for e in relu.entrees()))
        self.assertEqual(("bea",), relu.entree("Veille").proprietaires)

        fautif = self._fichier({"Nouvelle": self.PUBLIQUE, "Cassée": {**self.PRIVEE, "proprietaires": []}})
        env = {ENV_PROFILES_DB: str(self.annuaire.chemin)}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("rssresume.api.__main__.console.error") as erreur:
            self.assertEqual(2, api_main.main(["importer-catalogue", str(fautif)]))
        self.assertIn("Cassée", erreur.call_args.args[0])
        self.assertEqual(["Tech", "Veille"], sorted(e.libelle for e in self.annuaire.catalogue().entrees()))

    def test_the_command_line_imports_the_catalogue_into_the_declared_database(self):
        fichier = self._fichier({"_note": "commentaire", "Tech": self.PUBLIQUE, "Veille": self.PRIVEE})
        with mock.patch.dict(os.environ, {ENV_PROFILES_DB: str(self.annuaire.chemin)}, clear=True), \
                mock.patch("rssresume.api.__main__.console.log") as log:
            self.assertEqual(0, api_main.main(["importer-catalogue", str(fichier)]))
        self.assertIn("2 catégorie(s)", log.call_args.args[0])
        self.assertIn("1 privée(s)", log.call_args.args[0])
        self.assertFalse(self.annuaire.catalogue().ouvert)

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("rssresume.api.__main__.console.error"):
            self.assertEqual(2, api_main.main(["importer-catalogue", str(fichier)]))
        with mock.patch.dict(os.environ, {ENV_PROFILES_DB: str(self.annuaire.chemin)}, clear=True), \
                mock.patch("rssresume.api.__main__.console.error"):
            self.assertEqual(2, api_main.main(["importer-catalogue", str(self._fichier("{", "casse.json"))]))

    def test_a_corrupted_catalogue_row_fails_when_read(self):
        self.annuaire.remplacer_catalogue(Catalogue.depuis_document({"Veille": self.PRIVEE}, "test"))
        for contenu in (json.dumps({**self.PRIVEE, "proprietaires": []}), "{pas du json"):
            with self.subTest(contenu=contenu):
                with self.annuaire._connexion() as connexion:
                    connexion.execute("UPDATE categories SET document = ?", (contenu,))
                with self.assertRaises(ValueError) as leve:
                    self.annuaire.catalogue()
                self.assertIn("Veille", str(leve.exception))


if __name__ == "__main__":
    unittest.main()
