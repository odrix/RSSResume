"""L'API HTTP, contre un vrai serveur sur un port libre et une vraie base temporaire.

Ce que ces tests protègent : le contrat consommé par le site (statuts, formes JSON), le
jeton exigé partout et le refus de démarrer sans lui, et les barrières entre une URL
fabriquée et le système de fichiers.
"""

import dataclasses
import datetime
import http.client
import json
import os
import pathlib
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
import zoneinfo
from unittest import mock

from rssresume import newsletter, runlog
from rssresume.annuaire_sqlite import AnnuaireSqlite
from rssresume.api import __main__ as api_main
from rssresume.api.routes import LIEN_DESABONNEMENT_INVALIDE, LIEN_RETOUR_INVALIDE, RoutePassage
from rssresume.api.serveur import (
    ENV_API_TOKEN,
    TAILLE_MAX_CORPS,
    ApplicationApi,
    ServeurApi,
    valider_jeton,
)
from rssresume.api.sorties import Sorties
from rssresume.categories import Catalogue, CategorieCatalogue
from rssresume.desabonnement import OBJET_DESABONNEMENT, Desabonnement, Signataire
from rssresume.liens import lien_sur
from rssresume.newsletter import Lettre
from rssresume.profil import ENV_PROFILES_DB
from rssresume.retours import LONGUEUR_MAX_COMMENTAIRE, OBJET_RETOUR, LienRetour
from rssresume.scheduler import DailySchedule
from tests.support import make_config

JETON = "j" * 48
AUDIO = bytes(range(256)) * 40  # 10 240 octets, chacun reconnaissable à sa position


class ServeurTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self._tmp.name)
        self.annuaire = AnnuaireSqlite(self.tmpdir / "profils.sqlite3")
        self.sortie = self.tmpdir / "output"
        application = ApplicationApi(JETON, self.annuaire, Sorties(self.sortie))
        self.serveur = ServeurApi(("127.0.0.1", 0), application)
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        self.fil.start()
        self.base = f"http://127.0.0.1:{self.serveur.server_address[1]}"

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        self._tmp.cleanup()

    def appel(self, methode, chemin, corps=None, jeton=JETON, entetes=None):
        """(statut, en-têtes, corps brut), les erreurs HTTP sont des réponses comme les autres."""
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        requete = urllib.request.Request(self.base + chemin, data=donnees, method=methode)
        if jeton is not None:
            requete.add_header("Authorization", f"Bearer {jeton}")
        if donnees is not None:
            requete.add_header("Content-Type", "application/json")
        for nom, valeur in (entetes or {}).items():
            requete.add_header(nom, valeur)
        try:
            with urllib.request.urlopen(requete, timeout=5) as reponse:
                return reponse.status, reponse.headers, reponse.read()
        except urllib.error.HTTPError as erreur:
            with erreur:
                return erreur.code, erreur.headers, erreur.read()

    def json(self, methode, chemin, corps=None, **kwargs):
        statut, _, brut = self.appel(methode, chemin, corps, **kwargs)
        return statut, (json.loads(brut) if brut else None)


class AuthentificationTests(ServeurTestCase):
    def test_missing_or_wrong_token_is_refused(self):
        for jeton in (None, "faux", JETON + "x", JETON[:-1]):
            statut, entetes, brut = self.appel("GET", "/api/v1/profils", jeton=jeton)
            self.assertEqual(401, statut, jeton)
            self.assertIn("erreur", json.loads(brut))
            self.assertEqual("Bearer", entetes["WWW-Authenticate"])

    def test_the_right_token_is_accepted(self):
        self.assertEqual((200, []), self.json("GET", "/api/v1/profils"))

    def test_the_token_is_checked_before_routing(self):
        self.assertEqual(401, self.appel("GET", "/inconnu", jeton=None)[0])
        self.assertEqual(404, self.appel("GET", "/inconnu")[0])

    def test_the_server_refuses_to_start_without_a_long_token(self):
        for jeton in (None, "", "court", "x" * 31):
            with self.assertRaises(ValueError):
                valider_jeton(jeton)
            env = {ENV_PROFILES_DB: str(self.tmpdir / "p.sqlite3")}
            if jeton is not None:
                env[ENV_API_TOKEN] = jeton
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    ApplicationApi.from_env()
                self.assertEqual(2, api_main.main([]))
        self.assertEqual("x" * 32, valider_jeton("x" * 32))

    def test_the_server_refuses_to_start_without_the_database(self):
        with mock.patch.dict(os.environ, {ENV_API_TOKEN: JETON}, clear=True):
            with self.assertRaises(ValueError):
                ApplicationApi.from_env()

    def test_a_startup_failure_is_reported_on_both_streams(self):
        """Le refus de démarrer s'écrit sur stderr et sur stdout.

        Les agrégateurs classent par flux, et celui du déploiement peut ne montrer que la
        sortie standard : une erreur demeurée sur stderr se lit comme un conteneur qui
        boucle sans raison.
        """
        env = {ENV_API_TOKEN: "court", ENV_PROFILES_DB: str(self.tmpdir / "p.sqlite3")}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(api_main, "console") as suiveur:
                self.assertEqual(2, api_main.main([]))
        sur_stderr = suiveur.error.call_args.args[-1]
        sur_stdout = suiveur.log.call_args.args[-1]
        self.assertEqual(sur_stderr, sur_stdout)
        self.assertIn("démarrage impossible", sur_stderr)
        self.assertIn(ENV_API_TOKEN, sur_stderr)


class ProfilsTests(ServeurTestCase):
    BEA = {"username": "bea", "profil": "Veille", "stack": ["Traefik"], "email": ["b@example.com"], "prenom": "Bea"}

    def test_create_read_update_delete(self):
        statut, cree = self.json("POST", "/api/v1/profils", self.BEA)
        self.assertEqual(201, statut)
        self.assertEqual(
            {"id", "username", "profil", "stack", "email", "prenom", "securite", "modifie_le"},
            set(cree),
        )
        self.assertEqual(("bea", "Veille", ["Traefik"], ["b@example.com"], "Bea"),
                         (cree["username"], cree["profil"], cree["stack"], cree["email"], cree["prenom"]))

        self.assertEqual((200, cree), self.json("GET", "/api/v1/profils/bea"))

        statut, liste = self.json("GET", "/api/v1/profils")
        self.assertEqual(200, statut)
        self.assertEqual(
            [{"id": cree["id"], "username": "bea", "prenom": "Bea", "email": ["b@example.com"],
              "modifie_le": cree["modifie_le"]}],
            liste,
        )

        statut, modifie = self.json(
            "PUT", "/api/v1/profils/bea", {"profil": "Autre", "stack": [], "email": [], "prenom": ""}
        )
        self.assertEqual(200, statut)
        self.assertEqual((cree["id"], "bea", "Autre", []), (modifie["id"], modifie["username"], modifie["profil"], modifie["email"]))

        self.assertEqual(204, self.appel("DELETE", "/api/v1/profils/bea")[0])
        self.assertEqual(404, self.appel("GET", "/api/v1/profils/bea")[0])
        self.assertEqual((200, []), self.json("GET", "/api/v1/profils"))

    def test_the_list_is_sorted_by_username(self):
        for nom in ("zoe", "adrien", "bea"):
            self.json("POST", "/api/v1/profils", {"username": nom, "profil": nom})
        noms = [p["username"] for p in self.json("GET", "/api/v1/profils")[1]]
        self.assertEqual(["adrien", "bea", "zoe"], noms)

    def test_a_taken_name_is_a_conflict(self):
        self.json("POST", "/api/v1/profils", self.BEA)
        statut, corps = self.json("POST", "/api/v1/profils", self.BEA)
        self.assertEqual(409, statut)
        self.assertIn("bea", corps["erreur"])

    def test_invalid_documents_are_unprocessable_with_the_validation_message(self):
        for document in (
            {"username": "Bea", "profil": "x"},
            {"profil": "x"},
            {"username": "bea", "profil": ""},
            {"username": "bea", "profil": "x", "email": "pas-une-adresse"},
            {"username": "bea", "profil": "x", "prenom": 3},
            [1, 2],
        ):
            statut, corps = self.json("POST", "/api/v1/profils", document)
            self.assertEqual(422, statut, document)
            self.assertTrue(corps["erreur"])
        self.json("POST", "/api/v1/profils", self.BEA)
        self.assertEqual(422, self.json("PUT", "/api/v1/profils/bea", {"profil": ""})[0])
        self.assertEqual(422, self.json("PUT", "/api/v1/profils/bea", {"profil": "x", "username": "zoe"})[0])

    def test_an_unknown_security_regime_is_unprocessable(self):
        self.json("POST", "/api/v1/profils", self.BEA)

        statut, corps = self.json("PUT", "/api/v1/profils/bea", {"profil": "x", "securite": "expert"})

        self.assertEqual(422, statut)
        self.assertIn("securite", corps["erreur"])

    def test_a_refusal_names_the_faulty_field(self):
        self.json("POST", "/api/v1/profils", self.BEA)
        axes_trop_courts = [{"slug": "qualite", "libelle": "Qualité", "description": "tests"}]

        for document, champ in (
            ({"profil": "x", "securite": "expert"}, "securite"),
            ({"profil": "x", "axes": axes_trop_courts}, "axes"),
        ):
            with self.subTest(champ=champ):
                statut, corps = self.json("PUT", "/api/v1/profils/bea", document)
                self.assertEqual(422, statut)
                self.assertEqual(champ, corps["champ"])
                self.assertIn(champ, corps["erreur"])
        statut, corps = self.json("POST", "/api/v1/profils", {"username": "zoe", "profil": "x", "prenom": 3})
        self.assertEqual((422, "prenom"), (statut, corps["champ"]))
        # Un refus qui ne tient à aucune clé n'en invente pas.
        statut, corps = self.json("PUT", "/api/v1/profils/bea", [1, 2])
        self.assertEqual(422, statut)
        self.assertNotIn("champ", corps)

    def test_put_refuses_a_category_outside_the_catalogue_with_its_field(self):
        self.annuaire.remplacer_catalogue(Catalogue([
            CategorieCatalogue("Tech", "Tech.", ["developpeur"]),
            CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["bea"]),
            CategorieCatalogue("Veille interne", "Interne.", ["cto"], ["zoe"]),
        ]))
        self.assertEqual(201, self.json("POST", "/api/v1/profils", self.BEA)[0])

        for categorie in ("Inconnue", "Veille interne"):
            with self.subTest(categorie=categorie):
                statut, corps = self.json(
                    "PUT", "/api/v1/profils/bea", {"profil": "x", "categories": ["Tech", categorie]}
                )
                self.assertEqual(422, statut)
                self.assertEqual("categories", corps["champ"])
                self.assertNotIn("Veille interne,", corps["erreur"])
        self.assertNotIn("categories", self.json("GET", "/api/v1/profils/bea")[1])

        statut, modifie = self.json(
            "PUT", "/api/v1/profils/bea", {"profil": "x", "categories": ["tech", "Veille marché"]}
        )
        self.assertEqual(200, statut)
        self.assertEqual(["Tech", "Veille marché"], modifie["categories"])

    def test_put_keeps_a_followed_category_since_removed_from_the_catalogue(self):
        """Seul ce qu'on ajoute se vérifie : confirmer une adresse ne doit pas échouer parce
        qu'une catégorie suivie a quitté le catalogue, la tournée la refiltre."""
        self.annuaire.remplacer_catalogue(Catalogue([
            CategorieCatalogue("Tech", "Tech.", ["developpeur"]),
            CategorieCatalogue("Ancienne", "Retirée ensuite.", ["cto"]),
            CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["bea"]),
        ]))
        self.json("POST", "/api/v1/profils", {**self.BEA, "categories": ["Tech", "Ancienne", "Veille marché"]})
        # « Ancienne » disparaît, « Veille marché » passe à une autre propriétaire.
        self.annuaire.remplacer_catalogue(Catalogue([
            CategorieCatalogue("Tech", "Tech.", ["developpeur"]),
            CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["zoe"]),
        ]))

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Autre", "categories": ["Tech", "ancienne", "Veille marché"]
        })

        self.assertEqual(200, statut)
        self.assertEqual(["Tech", "Ancienne", "Veille marché"], modifie["categories"])
        # Retirée puis renvoyée, elle n'est plus acquise : c'est un ajout, vérifié.
        self.json("PUT", "/api/v1/profils/bea", {"profil": "Autre", "categories": ["Tech"]})
        statut, corps = self.json("PUT", "/api/v1/profils/bea", {"profil": "Autre", "categories": ["Ancienne"]})
        self.assertEqual((422, "categories"), (statut, corps["champ"]))

    def test_an_unreadable_catalogue_is_a_server_error_not_a_refusal(self):
        self.json("POST", "/api/v1/profils", self.BEA)
        connexion = sqlite3.connect(self.annuaire.chemin)
        try:
            connexion.execute(
                "INSERT INTO categories (libelle, document) VALUES (?, ?)", ("Tech", '{"description": ""}')
            )
            connexion.commit()
        finally:
            connexion.close()

        with mock.patch("rssresume.api.routes.console.error") as journal:
            for methode, chemin, corps in (
                ("PUT", "/api/v1/profils/bea", {"profil": "x"}),
                ("POST", "/api/v1/profils", {"username": "zoe", "profil": "x"}),
                ("GET", "/api/v1/profils/bea/categories", None),
            ):
                with self.subTest(methode=methode, chemin=chemin):
                    statut, reponse = self.json(methode, chemin, corps)
                    self.assertEqual(500, statut)
                    self.assertNotIn("champ", reponse)
                    self.assertNotIn("Tech", reponse["erreur"])
        self.assertEqual(3, journal.call_count)
        self.assertEqual("Veille", self.json("GET", "/api/v1/profils/bea")[1]["profil"])

    def test_the_security_regime_is_kept_and_read_back(self):
        self.json("POST", "/api/v1/profils", {**self.BEA, "securite": "decideur"})
        self.json("POST", "/api/v1/profils", {"username": "zoe", "profil": "Z"})

        self.assertEqual("decideur", self.json("GET", "/api/v1/profils/bea")[1]["securite"])
        # Sans clé, le défaut, celui que la tournée servira.
        self.assertEqual("exploitant", self.json("GET", "/api/v1/profils/zoe")[1]["securite"])

    def test_an_empty_axes_list_returns_to_default_axes(self):
        self.json("POST", "/api/v1/profils", {**self.BEA, "axes": [
            {"slug": "qualite", "libelle": "Qualité", "description": "tests et fiabilité"},
            {"slug": "livraison", "libelle": "Livraison", "description": "déploiement"},
            {"slug": "experience", "libelle": "Expérience", "description": "usage"},
        ]})

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Veille", "stack": [], "email": [], "prenom": "", "axes": []
        })

        self.assertEqual(200, statut)
        self.assertNotIn("axes", modifie)

    def test_an_empty_categories_list_returns_to_all_catalogue_categories(self):
        statut, _ = self.json("POST", "/api/v1/profils", {**self.BEA, "categories": ["Tech"]})
        self.assertEqual(201, statut)

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Veille", "stack": [], "email": [], "prenom": "", "categories": []
        })

        self.assertEqual(200, statut)
        self.assertNotIn("categories", modifie)

    def test_put_with_excluded_feeds_returns_them(self):
        self.json("POST", "/api/v1/profils", self.BEA)

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Veille", "flux_exclus": ["NoLimitSecu", "FreshRSS releases"]
        })

        self.assertEqual(200, statut)
        self.assertEqual(["NoLimitSecu", "FreshRSS releases"], modifie["flux_exclus"])
        self.assertEqual(
            ["NoLimitSecu", "FreshRSS releases"], self.json("GET", "/api/v1/profils/bea")[1]["flux_exclus"]
        )
        statut, corps = self.json("PUT", "/api/v1/profils/bea", {"profil": "Veille", "flux_exclus": "NoLimitSecu"})
        self.assertEqual(422, statut)
        self.assertIn("flux_exclus", corps["erreur"])

    def test_put_conserve_flux_exclus(self):
        """Un réglage venu d'un gabarit survit à un enregistrement « Mon profil » qui ne
        connaît pas la clé : le PUT fusionne, il ne remplace plus."""
        self.json("POST", "/api/v1/profils", {**self.BEA, "flux_exclus": ["NoLimitSecu"]})

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Veille", "stack": [], "email": [], "prenom": ""
        })

        self.assertEqual(200, statut)
        self.assertEqual(["NoLimitSecu"], modifie["flux_exclus"])
        self.assertEqual(
            ["NoLimitSecu"], self.json("GET", "/api/v1/profils/bea")[1]["flux_exclus"]
        )

    def test_put_conserve_une_cle_non_editee_par_le_site(self):
        """La fusion préserve ce que le site n'édite pas ; une clé hors format, même
        renvoyée dans le corps, reste hors document, pas de fuite."""
        self.json("POST", "/api/v1/profils", self.BEA)
        self.json("PUT", "/api/v1/profils/bea", {**self.BEA, "flux_exclus": ["NoLimitSecu"]})

        statut, modifie = self.json("PUT", "/api/v1/profils/bea", {
            "profil": "Autre", "stack": [], "email": [], "prenom": "", "inconnue": 1
        })

        self.assertEqual(200, statut)
        self.assertEqual(["NoLimitSecu"], modifie["flux_exclus"])
        self.assertEqual(200, self.appel("GET", "/api/v1/profils/bea")[0])
        self.assertNotIn("inconnue", self.json("GET", "/api/v1/profils/bea")[1])

    def test_unknown_profiles_are_not_found(self):
        self.assertEqual(404, self.appel("GET", "/api/v1/profils/absent")[0])
        self.assertEqual(404, self.appel("PUT", "/api/v1/profils/absent", {"profil": "x"})[0])
        self.assertEqual(404, self.appel("DELETE", "/api/v1/profils/absent")[0])
        self.assertEqual(404, self.appel("GET", "/api/v1/profils/absent/journees")[0])
        self.assertEqual(404, self.appel("GET", "/api/v1/profils/..%2F..%2Fetc/journees")[0])

    def test_an_unserved_method_is_not_allowed(self):
        statut, entetes, _ = self.appel("DELETE", "/api/v1/profils")
        self.assertEqual(405, statut)
        self.assertEqual("GET, POST", entetes["Allow"])

    def test_bad_bodies(self):
        statut, _, _ = self.appel(
            "POST", "/api/v1/profils", self.BEA, entetes={"Content-Type": "text/plain"}
        )
        self.assertEqual(400, statut)

        requete = urllib.request.Request(
            self.base + "/api/v1/profils", data=b"{pas du json", method="POST",
            headers={"Authorization": f"Bearer {JETON}", "Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as leve:
            urllib.request.urlopen(requete, timeout=5)
        self.assertEqual(400, leve.exception.code)
        leve.exception.close()

    def test_a_body_too_large_is_refused_before_being_read(self):
        connexion = http.client.HTTPConnection("127.0.0.1", self.serveur.server_address[1], timeout=5)
        try:
            connexion.putrequest("POST", "/api/v1/profils")
            connexion.putheader("Authorization", f"Bearer {JETON}")
            connexion.putheader("Content-Type", "application/json")
            connexion.putheader("Content-Length", str(TAILLE_MAX_CORPS + 1))
            connexion.endheaders()
            reponse = connexion.getresponse()
            self.assertEqual(413, reponse.status)
            self.assertIn("erreur", json.loads(reponse.read()))
        finally:
            connexion.close()
        self.assertEqual([], self.annuaire.usernames())


class JourneesTests(ServeurTestCase):
    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B"})
        dossier = self.sortie / self.fiche.id
        for jour, fichiers in (
            ("2026-08-22", {"journee.mp3": AUDIO, "Tech.log.json": b"{}"}),
            ("2026-08-23", {"Tech.wav": b"RIFF", "News.mp3": b"ID3"}),
            ("2026-08-24", {}),
        ):
            (dossier / jour).mkdir(parents=True)
            for nom, contenu in fichiers.items():
                (dossier / jour / nom).write_bytes(contenu)
        (dossier / "pas-une-date").mkdir()
        (dossier / "2026-13-45").mkdir()
        # Un secret à côté du dossier du profil : aucune URL ne doit l'atteindre.
        (self.sortie / "secret.mp3").write_bytes(b"secret")

    def audio(self, nom="journee.mp3", jour="2026-08-22", **kwargs):
        return self.appel("GET", f"/api/v1/profils/bea/journees/{jour}/audios/{nom}", **kwargs)

    def test_the_days_are_listed_most_recent_first_with_their_audios(self):
        statut, journees = self.json("GET", "/api/v1/profils/bea/journees")
        self.assertEqual(200, statut)
        self.assertEqual(
            [
                {"date": "2026-08-24", "audios": []},
                {"date": "2026-08-23", "audios": [{"nom": "News.mp3", "taille": 3}, {"nom": "Tech.wav", "taille": 4}]},
                {"date": "2026-08-22", "audios": [{"nom": "journee.mp3", "taille": len(AUDIO)}]},
            ],
            journees,
        )

    def test_a_profile_without_output_has_no_days(self):
        self.annuaire.creer("zoe", {"profil": "Z"})
        self.assertEqual((200, []), self.json("GET", "/api/v1/profils/zoe/journees"))

    def test_the_whole_audio(self):
        statut, entetes, corps = self.audio()
        self.assertEqual(200, statut)
        self.assertEqual(AUDIO, corps)
        self.assertEqual("audio/mpeg", entetes["Content-Type"])
        self.assertEqual("bytes", entetes["Accept-Ranges"])
        self.assertEqual(str(len(AUDIO)), entetes["Content-Length"])
        self.assertEqual("audio/wav", self.audio("Tech.wav", "2026-08-23")[1]["Content-Type"])

    def test_the_three_forms_of_range(self):
        taille = len(AUDIO)
        for plage, debut, fin in (
            ("bytes=100-199", 100, 199),
            ("bytes=10000-", 10000, taille - 1),
            ("bytes=-50", taille - 50, taille - 1),
            ("bytes=10200-99999", 10200, taille - 1),
        ):
            statut, entetes, corps = self.audio(entetes={"Range": plage})
            self.assertEqual(206, statut, plage)
            self.assertEqual(AUDIO[debut:fin + 1], corps, plage)
            self.assertEqual(f"bytes {debut}-{fin}/{taille}", entetes["Content-Range"])
            self.assertEqual(str(fin - debut + 1), entetes["Content-Length"])

    def test_a_range_outside_the_file_is_not_satisfiable(self):
        for plage in (f"bytes={len(AUDIO)}-", "bytes=999999-1000000", "bytes=-0"):
            statut, entetes, _ = self.audio(entetes={"Range": plage})
            self.assertEqual(416, statut, plage)
            self.assertEqual(f"bytes */{len(AUDIO)}", entetes["Content-Range"])

    def test_an_unreadable_range_serves_the_whole_file(self):
        for plage in ("octets=0-1", "bytes=5-2", "bytes=0-1,4-5"):
            statut, _, corps = self.audio(entetes={"Range": plage})
            self.assertEqual(200, statut, plage)
            self.assertEqual(AUDIO, corps)

    def test_path_traversal_and_foreign_files_are_not_found(self):
        for nom, jour in (
            ("..%2F..%2Fsecret.mp3", "2026-08-22"),
            ("..%5C..%5Csecret.mp3", "2026-08-22"),
            ("..", "2026-08-22"),
            ("Tech.log.json", "2026-08-22"),
            ("absent.mp3", "2026-08-22"),
            ("journee.mp3", "2026-08-21"),
            ("journee.mp3", "20260822"),
            ("journee.mp3", "2026-13-45"),
            ("journee.mp3", "..%2F.."),
            ("secret.mp3", "..%2F.."),
        ):
            self.assertEqual(404, self.audio(nom, jour)[0], (nom, jour))

    def _semer(self, nombre: int) -> None:
        """`nombre` journées de plus en septembre 2026, pour dépasser un lot de dix."""
        dossier = self.sortie / self.fiche.id
        for jour in range(1, nombre + 1):
            (dossier / f"2026-09-{jour:02d}").mkdir()

    def test_pagination_returns_a_lot_and_the_total_most_recent_first(self):
        self._semer(25)  # 28 journées au total avec celles du setUp
        statut, corps = self.json("GET", "/api/v1/profils/bea/journees?decalage=0&limite=10")
        self.assertEqual(200, statut)
        self.assertEqual(28, corps["total"])
        dates = [journee["date"] for journee in corps["journees"]]
        self.assertEqual(10, len(dates))
        self.assertEqual("2026-09-25", dates[0])
        self.assertEqual("2026-09-16", dates[-1])
        self.assertEqual(sorted(dates, reverse=True), dates)

    def test_pagination_walks_the_lots_in_order_until_the_end(self):
        self._semer(25)
        _, deuxieme = self.json("GET", "/api/v1/profils/bea/journees?decalage=10&limite=10")
        self.assertEqual(28, deuxieme["total"])
        self.assertEqual("2026-09-15", deuxieme["journees"][0]["date"])
        self.assertEqual(10, len(deuxieme["journees"]))
        _, dernier = self.json("GET", "/api/v1/profils/bea/journees?decalage=20&limite=10")
        self.assertEqual(28, dernier["total"])
        self.assertEqual(8, len(dernier["journees"]))
        self.assertEqual("2026-08-22", dernier["journees"][-1]["date"])

    def test_pagination_beyond_the_end_is_an_empty_lot_with_the_total(self):
        self._semer(25)
        statut, corps = self.json("GET", "/api/v1/profils/bea/journees?decalage=100&limite=10")
        self.assertEqual(200, statut)
        self.assertEqual({"journees": [], "total": 28}, corps)

    def test_pagination_accepts_a_single_parameter(self):
        self._semer(25)
        _, parLimite = self.json("GET", "/api/v1/profils/bea/journees?limite=2")
        self.assertEqual(2, len(parLimite["journees"]))
        self.assertEqual(28, parLimite["total"])
        _, parDecalage = self.json("GET", "/api/v1/profils/bea/journees?decalage=26")
        self.assertEqual(["2026-08-23", "2026-08-22"], [j["date"] for j in parDecalage["journees"]])
        self.assertEqual(28, parDecalage["total"])

    def test_pagination_parameters_must_be_valid_integers(self):
        for query in ("decalage=-1", "decalage=abc", "decalage=1.5", "limite=0", "limite=-3", "limite=x"):
            statut, corps = self.json("GET", f"/api/v1/profils/bea/journees?{query}")
            self.assertEqual(400, statut, query)
            self.assertIn("erreur", corps)


def wav_silencieux(chemin: pathlib.Path, secondes: int) -> None:
    """Un vrai `.wav`, pour que la durée se mesure : le reste du disque est factice."""
    with wave.open(str(chemin), "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(1)
        fichier.setframerate(100)
        fichier.writeframes(b"\x80" * 100 * secondes)


def journal_categorie(categorie, resume, articles, audio=None) -> bytes:
    """Un `<categorie>.log.json` réduit à ce que `runlog.read_day` en relit."""
    return json.dumps(
        {
            "categorie": categorie,
            "date": "2026-11-21",
            "resume": resume,
            "resultat": {"statut": "audio" if audio else "sans-audio", "audio": audio},
            "articles": articles,
        },
        ensure_ascii=False,
    ).encode("utf-8")


class LienSurTests(unittest.TestCase):
    def test_only_http_and_https_urls_pass(self):
        for url in ("https://exemple.test/a", "http://exemple.test/b?c=d#e", "HTTPS://Exemple.test/"):
            self.assertEqual(url, lien_sur(url), url)
        self.assertEqual("https://exemple.test/a", lien_sur("  https://exemple.test/a \n"))
        for url in (
            "javascript:alert(1)",
            " JaVaScRiPt:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "//hote/chemin",
            "ftp://exemple.test/fichier",
            "vbscript:msgbox",
            "https:///sans-hote",
            "http://[mal",
            "",
        ):
            self.assertIsNone(lien_sur(url), url)

    def test_an_inner_blank_or_control_character_is_refused(self):
        """`urlsplit` les retire avant d'analyser : l'URL passerait, le texte brut avec."""
        for url in (
            "https://a.test/x\n  javascript:alert(1)",
            "https://a.test/x\r\njavascript:alert(1)",
            "https://a.test/x\tjavascript:alert(1)",
            "https://a.test/x y",
            "https://a.test/x\x00",
            "https://a.test/ x",
        ):
            self.assertIsNone(lien_sur(url), repr(url))


class ContenuJourneeTests(ServeurTestCase):
    """`GET /api/v1/profils/{username}/journees/{date}` : la journée telle que l'email l'a portée."""

    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B"})
        self.dossier = self.sortie / self.fiche.id
        # Une journée par catégorie : un audio, deux articles retenus, un à surveiller.
        cyber = self.dossier / "2026-11-21"
        cyber.mkdir(parents=True)
        wav_silencieux(cyber / "1-cyber.wav", 300)
        (cyber / "1-cyber.log.json").write_bytes(
            journal_categorie(
                "Cybersécurité",
                "Premier paragraphe.\n\nSecond paragraphe.",
                [
                    {"item_id": "b", "titre": "Second", "flux": "Flux B",
                     "url": "https://exemple.test/b", "retenu": True, "rang_digest": 2, "score": 9},
                    {"item_id": "a", "titre": "Premier", "flux": "Flux A",
                     "url": "https://exemple.test/a", "retenu": True, "rang_digest": 1, "score": 8},
                    {"item_id": "c", "titre": "Presque", "flux": "Flux C",
                     "url": "https://exemple.test/c", "retenu": False, "score": 5},
                    {"item_id": "d", "titre": "Écarté", "flux": "Flux D",
                     "url": "https://exemple.test/d", "retenu": False, "score": 1},
                ],
                audio="1-cyber.wav",
            )
        )
        # Une journée en mode global : un seul audio, porté par la journée.
        globale = self.dossier / "2026-11-20"
        globale.mkdir()
        wav_silencieux(globale / "journee.wav", 720)
        (globale / "journee.json").write_text(
            json.dumps({"montage": {"texte": "Le montage.", "audio": "journee.wav"}}), encoding="utf-8"
        )
        (globale / "1-cyber.log.json").write_bytes(
            journal_categorie("Cybersécurité", "Le résumé.", [
                {"item_id": "a", "titre": "Premier", "flux": "Flux A",
                 "url": "https://exemple.test/a", "retenu": True, "rang_digest": 1, "score": 8},
            ])
        )
        # Une journée sans article : son seul marqueur, ni journal ni audio.
        vide = self.dossier / "2026-11-19"
        vide.mkdir()
        (vide / "1-cyber.no-article").write_text("", encoding="utf-8")

    def contenu(self, jour, username="bea", **kwargs):
        return self.json("GET", f"/api/v1/profils/{username}/journees/{jour}", **kwargs)

    def test_the_day_content_requires_the_token(self):
        for jeton in (None, "faux", JETON[:-1]):
            statut, entetes, brut = self.appel(
                "GET", "/api/v1/profils/bea/journees/2026-11-21", jeton=jeton
            )
            self.assertEqual(401, statut, jeton)
            self.assertNotIn("Cybersécurité", brut.decode("utf-8"))
        self.assertEqual(200, self.contenu("2026-11-21")[0])

    def test_unknown_days_and_forged_paths_are_not_found(self):
        (self.sortie / "2026-11-21").mkdir()  # à côté du dossier du profil, pas dedans
        self.annuaire.creer("zoe", {"profil": "Z"})
        for username, jour in (
            ("absent", "2026-11-21"),
            ("zoe", "2026-11-21"),
            ("bea", "2026-11-18"),
            ("bea", "20261121"),
            ("bea", "2026-13-45"),
            ("bea", "..%2F2026-11-21"),
            ("bea", "..%2F..%2F2026-11-21"),
            ("bea", "..%5C2026-11-21"),
            ("bea", "%2E%2E"),
        ):
            statut, corps = self.contenu(jour, username)
            self.assertEqual(404, statut, (username, jour))
            self.assertIn("erreur", corps)
        try:
            (self.dossier / "2026-11-17").symlink_to(self.sortie, target_is_directory=True)
        except OSError:
            return  # Windows sans le droit de créer un lien : le reste est vérifié
        self.assertEqual(404, self.contenu("2026-11-17")[0])

    def test_the_content_is_the_one_the_email_shows(self):
        statut, contenu = self.contenu("2026-11-21")
        self.assertEqual(200, statut)
        self.assertEqual(
            {
                "date": "2026-11-21",
                "audios": [{"nom": "1-cyber.wav", "taille": (self.dossier / "2026-11-21" / "1-cyber.wav").stat().st_size}],
                "ecoute": "5 min",
                "racontees": 1,
                "montage": None,
                "raison": None,
                "en_cours": False,
                "categories": [
                    {
                        "categorie": "Cybersécurité",
                        "racontee": True,
                        "resume": "Premier paragraphe.\n\nSecond paragraphe.",
                        "audio": "1-cyber.wav",
                        "ecoute": "5 min",
                        "articles": [
                            {"titre": "Premier", "source": "Flux A", "url": "https://exemple.test/a"},
                            {"titre": "Second", "source": "Flux B", "url": "https://exemple.test/b"},
                        ],
                        "a_surveiller": [
                            {"titre": "Presque", "source": "Flux C", "url": "https://exemple.test/c"},
                        ],
                    }
                ],
            },
            contenu,
        )
        # Et c'est bien ce que porte l'email renvoyé par `--send-only` : même lecture.
        jour = self.dossier / "2026-11-21"
        texte = Lettre.compose(
            datetime.date(2026, 11, 21), runlog.read_day(jour), montage=runlog.read_montage(jour)
        ).text
        for categorie in contenu["categories"]:
            self.assertIn(categorie["resume"].split("\n")[0], texte)
            for lien in categorie["articles"] + categorie["a_surveiller"]:
                self.assertIn(lien["url"], texte)
        self.assertNotIn("https://exemple.test/d", texte)

    def test_a_global_day_carries_its_montage(self):
        statut, contenu = self.contenu("2026-11-20")
        self.assertEqual(200, statut)
        self.assertEqual({"audio": "journee.wav", "ecoute": "12 min"}, contenu["montage"])
        self.assertEqual("12 min", contenu["ecoute"])
        categorie, = contenu["categories"]
        self.assertIsNone(categorie["audio"])
        self.assertEqual("Le résumé.", categorie["resume"])

    def test_a_day_without_article_is_listed_with_its_reason(self):
        statut, journees = self.json("GET", "/api/v1/profils/bea/journees")
        self.assertEqual(200, statut)
        self.assertIn({"date": "2026-11-19", "audios": []}, journees)

        statut, contenu = self.contenu("2026-11-19")
        self.assertEqual(200, statut)
        self.assertEqual([], contenu["categories"])
        self.assertEqual([], contenu["audios"])
        self.assertIsNone(contenu["montage"])
        self.assertEqual(
            f"Aucun article trouvé pour le {newsletter.date_longue(datetime.date(2026, 11, 19))}.",
            contenu["raison"],
        )
        self.assertIn("19 novembre 2026", contenu["raison"])
        self.assertFalse(contenu["en_cours"])

    def test_a_day_being_written_is_in_progress_not_an_error(self):
        """Un journal lu pendant que la tournée l'écrit est tronqué : ni 500, ni « aucun article »."""
        jour = self.dossier / "2026-11-21"
        complet = (jour / "1-cyber.log.json").read_bytes()
        for tronque in (complet[: len(complet) // 2], complet[:-1], b"", "é".encode("utf-8")[:1]):
            (jour / "2-tech.log.json").write_bytes(tronque)
            statut, contenu = self.contenu("2026-11-21")
            self.assertEqual(200, statut, tronque)
            self.assertTrue(contenu["en_cours"])
            self.assertIsNone(contenu["raison"])
            self.assertEqual([], contenu["categories"])
            self.assertEqual(["1-cyber.wav"], [audio["nom"] for audio in contenu["audios"]])

    def test_a_day_without_any_log_yet_is_in_progress(self):
        """Le répertoire existe avant le premier journal : vide, il n'est pas « sans article »."""
        (self.dossier / "2026-11-22").mkdir()
        statut, contenu = self.contenu("2026-11-22")
        self.assertEqual(200, statut)
        self.assertTrue(contenu["en_cours"])
        self.assertIsNone(contenu["raison"])
        self.assertIn({"date": "2026-11-22", "audios": []}, self.json("GET", "/api/v1/profils/bea/journees")[1])

    def test_foreign_schemes_are_removed_from_links(self):
        jour = self.dossier / "2026-11-16"
        jour.mkdir()
        (jour / "1-cyber.log.json").write_bytes(
            journal_categorie("Cybersécurité", "Résumé.", [
                {"item_id": "a", "titre": "<img src=x onerror=alert(1)>", "flux": "F",
                 "url": "javascript:alert(document.cookie)", "retenu": True, "rang_digest": 1, "score": 9},
                {"item_id": "b", "titre": "B", "flux": "F",
                 "url": " JaVaScRiPt:alert(1)", "retenu": True, "rang_digest": 2, "score": 9},
                {"item_id": "c", "titre": "C", "flux": "F",
                 "url": "data:text/html,<script>alert(1)</script>", "retenu": False, "score": 5},
                {"item_id": "d", "titre": "D", "flux": "F",
                 "url": "https://exemple.test/d", "retenu": False, "score": 4},
            ])
        )
        statut, contenu = self.contenu("2026-11-16")
        self.assertEqual(200, statut)
        categorie, = contenu["categories"]
        self.assertEqual([None, None], [lien["url"] for lien in categorie["articles"]])
        self.assertEqual([None, "https://exemple.test/d"], [lien["url"] for lien in categorie["a_surveiller"]])
        # Le titre reste brut : c'est au rendu de l'échapper, et le site le fait.
        self.assertEqual("<img src=x onerror=alert(1)>", categorie["articles"][0]["titre"])


class PassageTests(ServeurTestCase):
    """`GET /api/v1/passage` : de quoi dire à une personne quand arrive son premier résumé."""

    def setUp(self):
        super().setUp()
        self.serveur.application = ApplicationApi(
            JETON,
            self.annuaire,
            Sorties(self.sortie),
            DailySchedule(datetime.time(4, 0), zoneinfo.ZoneInfo("Europe/Paris")),
        )

    def test_the_next_run_is_announced(self):
        avant = datetime.datetime.now(datetime.timezone.utc)
        statut, passage = self.json("GET", "/api/v1/passage")
        self.assertEqual(200, statut)
        self.assertEqual({"heure", "fuseau", "prochain"}, set(passage))
        self.assertEqual(("04:00", "Europe/Paris"), (passage["heure"], passage["fuseau"]))
        prochain = datetime.datetime.fromisoformat(passage["prochain"])
        self.assertGreater(prochain, avant)
        self.assertLessEqual(prochain - avant, datetime.timedelta(days=1))
        local = prochain.astimezone(zoneinfo.ZoneInfo("Europe/Paris"))
        self.assertEqual((4, 0), (local.hour, local.minute))
        self.assertEqual(local.utcoffset(), prochain.utcoffset())
        self.assertEqual(401, self.appel("GET", "/api/v1/passage", jeton=None)[0])

    def test_from_env_reads_the_schedule(self):
        base = {ENV_API_TOKEN: JETON, ENV_PROFILES_DB: str(self.tmpdir / "p.sqlite3")}

        def passage_de(env):
            with mock.patch.dict(os.environ, {**base, **env}, clear=True):
                application = ApplicationApi.from_env()
            return next(r for r in application.routes if isinstance(r, RoutePassage)).passage

        passage = passage_de({"RSSRESUME_SCHEDULE": "05:30", "RSSRESUME_TIMEZONE": "America/New_York"})
        self.assertEqual(datetime.time(5, 30), passage.heure)
        self.assertEqual("America/New_York", str(passage.timezone))
        # Sans variable, l'heure du travailleur sans variable.
        passage = passage_de({})
        self.assertEqual(datetime.time(7, 0), passage.heure)
        self.assertEqual("Europe/Paris", str(passage.timezone))
        for env in ({"RSSRESUME_SCHEDULE": "25:99"}, {"RSSRESUME_TIMEZONE": "Nulle/Part"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                passage_de(env)


class DesabonnementApiTests(ServeurTestCase):
    """`POST /api/v1/desabonnements[/lecture]` : le lien de la lettre, relayé par le site.

    Ce que ces tests protègent : un jeton signé par le travailleur avec le même
    `RSSRESUME_API_TOKEN` est accepté ici, un jeton forgé ou déjà servi ne l'est pas, et
    la lecture ne change rien."""

    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B", "email": ["b@example.com", "c@example.com"]})
        # Signé « côté travailleur » : par l'abonnement de la lettre, sur la configuration
        # qu'aurait le passage du jour, avec le même secret que celui de l'API.
        config = dataclasses.replace(
            make_config(self.tmpdir),
            site_url="https://veille.example.com",
            cle_signature=JETON,
            username="bea",
            profil_id=self.fiche.id,
            smtp_to=["b@example.com", "c@example.com"],
        )
        self.lien = newsletter.Abonnement.depuis_config(config).lien_desabonnement
        self.jeton = self.lien.rsplit("/", 1)[1]

    def test_reading_then_unsubscribing_then_the_link_is_spent(self):
        lecture = "/api/v1/desabonnements/lecture"
        self.assertEqual(
            (200, {"username": "bea", "destinataires": 2}), self.json("POST", lecture, {"jeton": self.jeton})
        )
        # La lecture n'a rien changé.
        self.assertEqual(["b@example.com", "c@example.com"], self.annuaire.fiche("bea").document["email"])

        self.assertEqual((200, {"username": "bea"}), self.json("POST", "/api/v1/desabonnements", {"jeton": self.jeton}))
        self.assertNotIn("email", self.annuaire.fiche("bea").document)

        refus = (404, {"erreur": LIEN_DESABONNEMENT_INVALIDE})
        self.assertEqual(refus, self.json("POST", "/api/v1/desabonnements", {"jeton": self.jeton}))
        self.assertEqual(refus, self.json("POST", lecture, {"jeton": self.jeton}))

    def test_a_forged_or_malformed_token_is_not_found(self):
        forge = Desabonnement(Signataire("x" * 48, OBJET_DESABONNEMENT)).jeton(
            self.fiche.id, ["b@example.com", "c@example.com"]
        )
        for corps in ({"jeton": forge}, {"jeton": self.jeton + "x"}, {"jeton": 3}, {}, ["jeton"]):
            for chemin in ("/api/v1/desabonnements", "/api/v1/desabonnements/lecture"):
                with self.subTest(corps=corps, chemin=chemin):
                    self.assertEqual(404, self.json("POST", chemin, corps)[0])
        self.assertEqual(["b@example.com", "c@example.com"], self.annuaire.fiche("bea").document["email"])

    def test_the_bearer_is_still_required(self):
        for chemin in ("/api/v1/desabonnements", "/api/v1/desabonnements/lecture"):
            self.assertEqual(401, self.appel("POST", chemin, {"jeton": self.jeton}, jeton=None)[0])
        self.assertIn("email", self.annuaire.fiche("bea").document)

    def test_a_link_survives_a_recipient_added_after_sending(self):
        """La liste vit après l'envoi : une adresse ajoutée ne rend pas caduc le lien des lettres parties."""
        self.annuaire.modifier(
            "bea", {"profil": "B", "email": ["b@example.com", "c@example.com", "d@example.com"]}
        )

        self.assertEqual(
            (200, {"username": "bea", "destinataires": 3}),
            self.json("POST", "/api/v1/desabonnements/lecture", {"jeton": self.jeton}),
        )
        self.assertEqual((200, {"username": "bea"}), self.json("POST", "/api/v1/desabonnements", {"jeton": self.jeton}))

    def test_a_single_address_stored_as_a_string_is_read_like_the_worker_does(self):
        document = {**self.fiche.document, "email": "a@x.fr"}
        with self.annuaire._connexion() as connexion:
            connexion.execute("UPDATE profils SET document = ? WHERE id = ?", (json.dumps(document), self.fiche.id))
        jeton = Desabonnement(Signataire(JETON, OBJET_DESABONNEMENT)).jeton(
            self.fiche.id, self.annuaire.profil("bea").emails
        )

        self.assertEqual(
            (200, {"username": "bea", "destinataires": 1}),
            self.json("POST", "/api/v1/desabonnements/lecture", {"jeton": jeton}),
        )
        self.assertEqual((200, {"username": "bea"}), self.json("POST", "/api/v1/desabonnements", {"jeton": jeton}))
        self.assertNotIn("email", self.annuaire.fiche("bea").document)

    def test_only_post_is_served(self):
        statut, entetes, _ = self.appel("GET", "/api/v1/desabonnements")
        self.assertEqual(405, statut)
        self.assertEqual("POST", entetes["Allow"])


class RetoursApiTests(ServeurTestCase):
    """Les retours « utile / pas utile » : par le lien de la lettre, par le site, et leur liste.

    Ce que ces tests protègent : un jeton signé par le travailleur vaut pour son profil et sa
    journée et pour rien d'autre, un jeton altéré ou d'un profil disparu reçoit le même 404,
    la lecture n'écrit rien, et un second vote, d'où qu'il vienne, remplace le premier."""

    JOUR = datetime.date(2026, 11, 22)

    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B", "email": ["b@example.com"]})
        self.autre = self.annuaire.creer("cle", {"profil": "C"})
        # Signé « côté travailleur » : par l'abonnement de la lettre, avec le secret de l'API.
        config = dataclasses.replace(
            make_config(self.tmpdir),
            site_url="https://veille.example.com",
            cle_signature=JETON,
            username="bea",
            profil_id=self.fiche.id,
        )
        lien = newsletter.Abonnement.depuis_config(config).liens_avis(self.JOUR)[0].url
        self.jeton = lien.rsplit("/", 1)[1].split("?")[0]

    def _lignes(self):
        with self.annuaire._connexion() as connexion:
            return connexion.execute("SELECT profil_id, jour, avis, commentaire FROM retours").fetchall()

    def test_reading_the_link_writes_nothing(self):
        self.assertEqual(
            (200, {"username": "bea", "jour": "2026-11-22", "retour": None}),
            self.json("POST", "/api/v1/retours/lecture", {"jeton": self.jeton}),
        )
        self.assertEqual([], self._lignes())

    def test_a_vote_by_link_is_written_for_the_profile_and_day_of_the_token(self):
        statut, corps = self.json(
            "POST",
            "/api/v1/retours",
            # Un corps qui tente de viser un autre profil et un autre jour : ignorés.
            {"jeton": self.jeton, "avis": "pas_utile", "commentaire": "Trop long.",
             "profil_id": self.autre.id, "jour": "2026-01-01", "username": "cle"},
        )

        self.assertEqual(200, statut)
        self.assertEqual(("bea", "2026-11-22"), (corps["username"], corps["jour"]))
        self.assertEqual(
            ("bea", "2026-11-22", "pas_utile", "Trop long."),
            tuple(corps["retour"][cle] for cle in ("username", "jour", "avis", "commentaire")),
        )
        self.assertEqual([(self.fiche.id, "2026-11-22", "pas_utile", "Trop long.")], self._lignes())
        # La lecture rend maintenant le vote, que la page pré-remplit.
        _, lecture = self.json("POST", "/api/v1/retours/lecture", {"jeton": self.jeton})
        self.assertEqual("Trop long.", lecture["retour"]["commentaire"])

    def test_an_altered_token_or_a_deleted_profile_is_the_same_404(self):
        refus = (404, {"erreur": LIEN_RETOUR_INVALIDE})
        corps_id, _, signature = self.jeton.rpartition(".")
        forges = (
            self.jeton.replace(self.fiche.id, self.autre.id),
            self.jeton.replace("2026-11-22", "2026-11-21"),
            corps_id + "." + signature[::-1],
            LienRetour(Signataire("x" * 48, OBJET_RETOUR)).jeton(self.fiche.id, self.JOUR),
            # Le jeton de désabonnement de la même lettre, même secret : un autre usage.
            Desabonnement(Signataire(JETON, OBJET_DESABONNEMENT)).jeton(self.fiche.id, ["b@example.com"]),
        )
        for corps in [*({"jeton": forge, "avis": "utile"} for forge in forges), {"jeton": 3}, {}, ["x"]]:
            for chemin in ("/api/v1/retours", "/api/v1/retours/lecture"):
                with self.subTest(corps=corps, chemin=chemin):
                    self.assertEqual(refus, self.json("POST", chemin, corps))

        self.annuaire.supprimer("bea")
        for chemin in ("/api/v1/retours", "/api/v1/retours/lecture"):
            self.assertEqual(refus, self.json("POST", chemin, {"jeton": self.jeton, "avis": "utile"}))
        self.assertEqual([], self._lignes())

    def test_a_refused_entry_names_its_field(self):
        for corps, champ in (
            ({"avis": "moyen"}, "avis"),
            ({"avis": "utile", "commentaire": "x" * (LONGUEUR_MAX_COMMENTAIRE + 1)}, "commentaire"),
        ):
            with self.subTest(champ=champ):
                statut, reponse = self.json("POST", "/api/v1/retours", {"jeton": self.jeton, **corps})
                self.assertEqual((422, champ), (statut, reponse["champ"]))
                statut, reponse = self.json("PUT", "/api/v1/profils/bea/journees/2026-11-22/retour", corps)
                self.assertEqual((422, champ), (statut, reponse["champ"]))
        self.assertEqual([], self._lignes())

    def test_a_vote_from_the_site_replaces_the_vote_from_the_letter(self):
        self.json("POST", "/api/v1/retours", {"jeton": self.jeton, "avis": "utile", "commentaire": "Lettre."})

        statut, retour = self.json(
            "PUT", "/api/v1/profils/bea/journees/2026-11-22/retour", {"avis": "pas_utile", "commentaire": "Site."}
        )

        self.assertEqual((200, "pas_utile", "Site."), (statut, retour["avis"], retour["commentaire"]))
        self.assertEqual([(self.fiche.id, "2026-11-22", "pas_utile", "Site.")], self._lignes())
        self.assertEqual(
            (200, "Site."),
            (lambda s, r: (s, r["commentaire"]))(*self.json("GET", "/api/v1/profils/bea/journees/2026-11-22/retour")),
        )

    def test_reading_a_day_without_vote_an_unknown_profile_or_a_bad_date_is_not_found(self):
        for chemin in (
            "/api/v1/profils/bea/journees/2026-11-22/retour",
            "/api/v1/profils/inconnu/journees/2026-11-22/retour",
            "/api/v1/profils/bea/journees/2026-02-30/retour",
            "/api/v1/profils/bea/journees/20261122/retour",
        ):
            with self.subTest(chemin=chemin):
                self.assertEqual(404, self.json("GET", chemin)[0])
        self.assertEqual(404, self.json("PUT", "/api/v1/profils/bea/journees/hier/retour", {"avis": "utile"})[0])

    def test_the_list_is_most_recent_first(self):
        with mock.patch("rssresume.annuaire_sqlite._maintenant", return_value="2026-11-22T07:00:00+00:00"):
            self.json("POST", "/api/v1/retours", {"jeton": self.jeton, "avis": "utile"})
        with mock.patch("rssresume.annuaire_sqlite._maintenant", return_value="2026-11-23T07:00:00+00:00"):
            self.json("PUT", "/api/v1/profils/cle/journees/2026-11-21/retour", {"avis": "pas_utile", "commentaire": "<b>"})

        statut, liste = self.json("GET", "/api/v1/retours")

        self.assertEqual(200, statut)
        self.assertEqual(
            [
                {"username": "cle", "jour": "2026-11-21", "avis": "pas_utile", "commentaire": "<b>",
                 "vote_le": "2026-11-23T07:00:00+00:00"},
                {"username": "bea", "jour": "2026-11-22", "avis": "utile", "commentaire": "",
                 "vote_le": "2026-11-22T07:00:00+00:00"},
            ],
            liste,
        )

    def test_the_bearer_is_still_required(self):
        for methode, chemin in (
            ("POST", "/api/v1/retours"),
            ("POST", "/api/v1/retours/lecture"),
            ("GET", "/api/v1/retours"),
            ("PUT", "/api/v1/profils/bea/journees/2026-11-22/retour"),
        ):
            with self.subTest(chemin=chemin):
                corps = None if methode == "GET" else {"jeton": self.jeton, "avis": "utile"}
                self.assertEqual(401, self.appel(methode, chemin, corps, jeton=None)[0])
        self.assertEqual([], self._lignes())


class GabaritsApiTests(ServeurTestCase):
    """`GET /api/v1/gabarits` expose les neuf professions au site."""

    def test_the_templates_endpoint_returns_the_profession_templates(self):
        statut, gabarits = self.json("GET", "/api/v1/gabarits")

        self.assertEqual(200, statut)
        metiers = {gabarit["metier"] for gabarit in gabarits}
        self.assertEqual(
            {"cto", "developpeur", "ops", "dsi", "rssi", "chef-de-projet", "qa", "po-pm", "designer"},
            metiers,
        )


class CategoriesApiTests(ServeurTestCase):
    """`GET /api/v1/profils/{username}/categories` : ce que la page profil propose de cocher."""

    def setUp(self):
        super().setUp()
        self.annuaire.remplacer_catalogue(Catalogue([
            CategorieCatalogue("Tech", "L'actualité technique.", ["developpeur"]),
            CategorieCatalogue("Veille marché", "Les concurrents.", ["cto"], ["bea"]),
            CategorieCatalogue("Veille interne", "Interne.", ["cto"], ["zoe"]),
        ]))

    def test_only_the_categories_a_profile_may_follow_are_listed(self):
        # Le profil n'a pas besoin d'exister : la page s'affiche avant de le créer.
        statut, proposees = self.json("GET", "/api/v1/profils/bea/categories")

        self.assertEqual(200, statut)
        self.assertEqual(
            {
                "ouvert": False,
                "categories": [
                    {"libelle": "Tech", "description": "L'actualité technique.", "privee": False},
                    {"libelle": "Veille marché", "description": "Les concurrents.", "privee": True},
                ],
            },
            proposees,
        )
        self.assertNotIn("proprietaires", json.dumps(proposees))
        self.assertNotIn("zoe", json.dumps(proposees))
        self.assertEqual(401, self.appel("GET", "/api/v1/profils/bea/categories", jeton=None)[0])

    def test_an_open_catalogue_lists_nothing_and_says_so(self):
        self.annuaire.remplacer_catalogue(Catalogue())

        self.assertEqual(
            (200, {"ouvert": True, "categories": []}), self.json("GET", "/api/v1/profils/bea/categories")
        )

    def test_an_invalid_username_is_not_found(self):
        for nom in ("Bea", "..%2F..%2Fetc", "a"):
            with self.subTest(nom=nom):
                self.assertEqual(404, self.appel("GET", f"/api/v1/profils/{nom}/categories")[0])
        statut, entetes, _ = self.appel("PUT", "/api/v1/profils/bea/categories", {"categories": []})
        self.assertEqual((405, "GET"), (statut, entetes["Allow"]))


class CoutsApiTests(ServeurTestCase):
    """Les coûts lus des journaux, sans appel au fournisseur ni recalcul tarifaire."""

    def setUp(self):
        super().setUp()
        self.fiche = self.annuaire.creer("bea", {"profil": "B"})

    def test_couts_sept_et_trente_jours_additionnent_les_journaux(self):
        dossier = self.sortie / self.fiche.id
        today = datetime.date.today()
        for jour, cout in ((today, 0.001), (today - datetime.timedelta(days=6), 0.002),
                           (today - datetime.timedelta(days=20), 0.003)):
            cible = dossier / jour.isoformat()
            cible.mkdir(parents=True)
            (cible / f"tech{runlog.LOG_SUFFIX}").write_text(json.dumps({
                "categorie": "Tech", "couts": {"appels": [{
                    "type_appel": "resume", "modele": "gpt-4o-mini",
                    "tokens_entree": 100, "tokens_sortie": 50, "cout": cout,
                }]}
            }), encoding="utf-8")

        statut, corps = self.json("GET", "/api/v1/profils/bea/couts")
        self.assertEqual(200, statut)
        self.assertAlmostEqual(0.003, corps["couts_7j"]["total"])
        self.assertAlmostEqual(0.006, corps["couts_30j"]["total"])
        self.assertTrue(corps["couts_7j"]["tarification_complete"])

    def test_modele_non_tarife_est_signale(self):
        dossier = self.sortie / self.fiche.id / datetime.date.today().isoformat()
        dossier.mkdir(parents=True)
        (dossier / f"tech{runlog.LOG_SUFFIX}").write_text(json.dumps({
            "categorie": "Tech", "couts": {"appels": [{
                "type_appel": "resume", "modele": "modele-maison",
                "cout": None,
            }]}
        }), encoding="utf-8")

        statut, corps = self.json("GET", "/api/v1/profils/bea/couts")
        self.assertEqual(200, statut)
        self.assertIsNone(corps["couts_7j"]["total"])
        self.assertIn("modele-maison", corps["couts_7j"]["modeles_sans_tarif"])


if __name__ == "__main__":
    unittest.main()
