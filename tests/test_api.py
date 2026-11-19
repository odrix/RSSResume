"""L'API HTTP, contre un vrai serveur sur un port libre et une vraie base temporaire.

Ce que ces tests protègent : le contrat consommé par le site (statuts, formes JSON), le
jeton exigé partout et le refus de démarrer sans lui, et les barrières entre une URL
fabriquée et le système de fichiers.
"""

import http.client
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from rssresume.annuaire_sqlite import AnnuaireSqlite
from rssresume.api import __main__ as api_main
from rssresume.api.serveur import (
    ENV_API_TOKEN,
    TAILLE_MAX_CORPS,
    ApplicationApi,
    ServeurApi,
    valider_jeton,
)
from rssresume.api.sorties import Sorties
from rssresume.profil import ENV_PROFILES_DB

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
        """(statut, en-têtes, corps brut) — les erreurs HTTP sont des réponses comme les autres."""
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


class ProfilsTests(ServeurTestCase):
    BEA = {"username": "bea", "profil": "Veille", "stack": ["Traefik"], "email": ["b@example.com"], "prenom": "Bea"}

    def test_create_read_update_delete(self):
        statut, cree = self.json("POST", "/api/v1/profils", self.BEA)
        self.assertEqual(201, statut)
        self.assertEqual(
            {"id", "username", "profil", "stack", "email", "prenom", "modifie_le"}, set(cree)
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


if __name__ == "__main__":
    unittest.main()
