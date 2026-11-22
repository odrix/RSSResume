"""Plusieurs profils sur un même FreshRSS : qui est servi, où, sous quels tags, et quand
la journée est marquée lue.

Ce que ces tests protègent :

- la provenance des profils (`Annuaire`) : un nom de fichier qui ne peut pas nommer un
  répertoire ni un préfixe de tags est refusé, et deux sources posées ensemble aussi ;
- l'isolement : un profil en échec ne coûte pas la journée des suivants ;
- le piège du marquage lu : l'état « lu » est unique dans FreshRSS, et le premier profil
  qui marquerait viderait la journée de tous ceux qui le suivent.
"""

import datetime as dt
import json
import os
import pathlib
import tempfile
import unittest
import uuid
from unittest import mock

from rssresume.digest import DigestService
from rssresume.external.freshrss import LABEL_STREAM_PREFIX, Etiquettes, FreshRSSClient
from rssresume.models import Article, Note
from rssresume.profil import (
    CLE_ID,
    ENV_PROFIL,
    ENV_PROFIL_FILE,
    ENV_PROFILES_DIR,
    Annuaire,
    AnnuaireDossier,
    AnnuaireFichier,
    AnnuaireVide,
    Lecteur,
    Profil,
    Securite,
    charger_profil,
    id_valide,
    lister_profils,
    nouvel_id,
    profil_depuis_dict,
    username_valide,
    valider_username,
)
from rssresume.summaries import SummaryGenerator
from rssresume.tournee import Tournee
from tests.support import FakeAudioGenerator, FakeEmailSender, FakeFreshRSSClient, make_config

JOUR = dt.date(2026, 8, 23)
ID_BEA = "5f0c2d8e-7a1b-4c3d-9e8f-0a1b2c3d4e5f"


def ecrire(dossier, nom, document):
    chemin = pathlib.Path(dossier) / nom
    contenu = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def article(item_id, tags=()):
    return Article(
        item_id=item_id,
        category="Tech",
        title=f"Titre {item_id}",
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text="Contenu.",
        tags=tags,
    )


class UsernameTests(unittest.TestCase):
    def test_valid_names(self):
        for nom in ("adrien", "a1", "bea_martin", "x-2", "0abc"):
            self.assertTrue(username_valide(nom), nom)
            self.assertEqual(nom, valider_username(nom))

    def test_invalid_names(self):
        """Un nom devient un répertoire et un préfixe de label : ni majuscule, ni espace,
        ni point, ni séparateur en tête, et pas plus de 32 caractères."""
        for nom in ("a", "Adrien", "jean paul", "-adrien", "_x", "a.b", "a" * 33, "", None, 12):
            self.assertFalse(username_valide(nom), nom)
            with self.assertRaises(ValueError):
                valider_username(nom)


class ProfilDepuisDictTests(unittest.TestCase):
    """La validation publique, celle que le site appellera avant d'écrire un fichier."""

    def test_a_complete_document_is_read(self):
        profil = profil_depuis_dict(
            {"profil": " Veille ", "stack": ["Traefik"], "email": "a@example.com", "prenom": "Bea"}
        )

        self.assertIsInstance(profil, Profil)
        self.assertEqual("Veille", profil.texte)
        self.assertEqual(("a@example.com",), profil.emails)
        self.assertEqual("Bea", profil.prenom)
        self.assertEqual(1, len(profil.stack))

    def test_every_fault_is_a_value_error_with_the_origin(self):
        for document in (
            [],
            {"profil": ""},
            {"profil": "x", "email": "pas-une-adresse"},
            {"profil": "x", "prenom": 3},
            {"profil": "x", "stack": [{"alias": ["sans nom"]}]},
        ):
            with self.assertRaises(ValueError) as leve:
                profil_depuis_dict(document, origine="bea")
            self.assertIn("bea", str(leve.exception))


class IdentifiantTests(unittest.TestCase):
    """La clé `id` : un UUID canonique, qui nomme la sortie et que l'API partagera."""

    def test_a_new_id_is_a_canonical_uuid4(self):
        identifiant = nouvel_id()

        self.assertTrue(id_valide(identifiant))
        self.assertEqual(4, uuid.UUID(identifiant).version)
        self.assertNotEqual(identifiant, nouvel_id())

    def test_only_the_canonical_lowercase_form_is_valid(self):
        for valeur in (ID_BEA.upper(), "{" + ID_BEA + "}", ID_BEA.replace("-", ""), "x", 3, None):
            self.assertFalse(id_valide(valeur), valeur)

    def test_the_document_id_is_read_and_checked(self):
        self.assertEqual(ID_BEA, profil_depuis_dict({CLE_ID: ID_BEA, "profil": "B"}).id)
        self.assertEqual("", profil_depuis_dict({"profil": "B"}).id)
        with self.assertRaises(ValueError):
            profil_depuis_dict({CLE_ID: "pas-un-uuid", "profil": "B"})
        with self.assertRaises(ValueError):
            profil_depuis_dict({CLE_ID: ID_BEA.upper(), "profil": "B"})

    def test_a_missing_id_is_generated_and_written_back_keeping_the_other_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = ecrire(tmpdir, "bea.json", {"profil": "Veille", "email": "b@example.com", "_note": "é"})

            premier = charger_profil(pathlib.Path(tmpdir), "bea")
            second = charger_profil(pathlib.Path(tmpdir), "bea")

            self.assertTrue(id_valide(premier.id))
            self.assertEqual(premier.id, second.id)
            texte = fichier.read_text(encoding="utf-8")
            relu = json.loads(texte)
            self.assertEqual(premier.id, relu[CLE_ID])
            self.assertEqual({CLE_ID, "profil", "email", "_note"}, set(relu))
            # Indenté, et lisible tel quel par qui édite le fichier à la main.
            self.assertIn('\n  "profil": "Veille"', texte)
            self.assertIn("é", texte)

    def test_a_plain_text_document_cannot_carry_an_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "bea.json", "Un profil en texte brut")

            with self.assertRaises(ValueError) as leve:
                charger_profil(pathlib.Path(tmpdir), "bea")
            self.assertIn("JSON", str(leve.exception))

    def test_duplicate_ids_are_refused_on_both_sides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "adrien.json", {CLE_ID: ID_BEA, "profil": "A"})
            ecrire(tmpdir, "bea.json", {CLE_ID: ID_BEA, "profil": "B"})
            ecrire(tmpdir, "carl.json", {"profil": "C"})
            annuaire = AnnuaireDossier(pathlib.Path(tmpdir))

            for nom in ("adrien", "bea"):
                with self.assertRaises(ValueError):
                    annuaire.lecteur(nom)
            self.assertTrue(id_valide(annuaire.lecteur("carl").id))


class AnnuaireDossierTests(unittest.TestCase):
    def test_the_profiles_are_listed_sorted_and_other_files_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "bea.json", {"profil": "B"})
            ecrire(tmpdir, "adrien.json", {"profil": "A"})
            ecrire(tmpdir, "README.md", "pas un profil")

            self.assertEqual(["adrien", "bea"], lister_profils(pathlib.Path(tmpdir)))
            self.assertEqual("B", charger_profil(pathlib.Path(tmpdir), "bea").texte)

    def test_a_json_file_with_an_invalid_name_is_reported_and_skipped(self):
        """Sauté : il ne coûte pas la journée des autres. Signalé une fois : sans un mot,
        il ferait disparaître une personne de la tournée."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "adrien.json", {"profil": "A"})
            ecrire(tmpdir, "Jean Paul.json", {"profil": "J"})
            annuaire = AnnuaireDossier(pathlib.Path(tmpdir))

            with mock.patch("rssresume.profil.console.error") as erreur:
                self.assertEqual(["adrien"], annuaire.usernames())
                self.assertEqual(["adrien"], annuaire.usernames())

            erreur.assert_called_once()
            message = erreur.call_args.args[0]
            self.assertIn("Jean Paul.json", message)
            self.assertIn("minuscules", message)

    def test_a_missing_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                lister_profils(pathlib.Path(tmpdir) / "absent")

    def test_an_empty_directory_serves_nobody(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual([], lister_profils(pathlib.Path(tmpdir)))

    def test_a_faulty_document_fails_only_its_own_reading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "adrien.json", {"profil": "A"})
            ecrire(tmpdir, "bea.json", '{"profil": ')
            annuaire = AnnuaireDossier(pathlib.Path(tmpdir))

            self.assertEqual(["adrien", "bea"], annuaire.usernames())
            self.assertEqual("A", annuaire.lecteur("adrien").profil.texte)
            with self.assertRaises(ValueError):
                annuaire.lecteur("bea")

    def test_targeting_an_unknown_profile_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire(tmpdir, "adrien.json", {"profil": "A"})
            annuaire = AnnuaireDossier(pathlib.Path(tmpdir))

            self.assertEqual(["adrien"], annuaire.cibles("adrien"))
            self.assertEqual(["adrien"], annuaire.cibles())
            with self.assertRaises(ValueError):
                annuaire.cibles("bea")


class DepuisEnvTests(unittest.TestCase):
    def test_the_directory_variable_selects_the_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {ENV_PROFILES_DIR: tmpdir}, clear=True):
                annuaire = Annuaire.depuis_env()
            self.assertIsInstance(annuaire, AnnuaireDossier)

    def test_the_single_file_is_the_only_profile_named_after_it(self):
        """Compatibilité : `input/adrien.json` sert `adrien`, sous `output/adrien/`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = ecrire(tmpdir, "adrien.json", {"profil": "A", "email": "a@example.com"})
            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                annuaire = Annuaire.depuis_env()

            self.assertIsInstance(annuaire, AnnuaireFichier)
            self.assertEqual(["adrien"], annuaire.usernames())
            self.assertEqual(("a@example.com",), annuaire.lecteur("adrien").profil.emails)

    def test_a_single_file_whose_name_is_not_a_username_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = ecrire(tmpdir, "Mon Profil.json", {"profil": "A"})
            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                with self.assertRaises(ValueError):
                    Annuaire.depuis_env()

    def test_nothing_declared_serves_nobody(self):
        """Plus de profil générique servi par défaut : pas d'action, pas de résumé."""
        with mock.patch.dict(os.environ, {}, clear=True):
            annuaire = Annuaire.depuis_env()

        self.assertIsInstance(annuaire, AnnuaireVide)
        self.assertEqual([], annuaire.usernames())
        self.assertEqual([], annuaire.cibles())
        with self.assertRaises(ValueError):
            annuaire.cibles("adrien")

    def test_an_inline_profile_is_refused_rather_than_ignored(self):
        """Ignorée, elle ferait cesser le digest d'une installation sans un mot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = ecrire(tmpdir, "adrien.json", {"profil": "A"})
            for env in ({ENV_PROFIL: "texte"}, {ENV_PROFIL: "texte", ENV_PROFIL_FILE: str(fichier)}):
                with mock.patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(ValueError) as leve:
                        Annuaire.depuis_env()
                self.assertIn(ENV_PROFIL, str(leve.exception))

    def test_the_directory_and_a_single_profile_together_fail_at_launch(self):
        for unique in (ENV_PROFIL_FILE, ENV_PROFIL):
            with tempfile.TemporaryDirectory() as tmpdir:
                env = {ENV_PROFILES_DIR: tmpdir, unique: "input/adrien.json"}
                with mock.patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(ValueError) as leve:
                        Annuaire.depuis_env()
                self.assertIn(unique, str(leve.exception))


class ConfigPourTests(unittest.TestCase):
    def test_the_personal_part_comes_from_the_profile_and_the_output_descends(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lecteur = Lecteur(
                "bea", Profil("Profil B", emails=["b@example.com"], prenom="Bea", identifiant=ID_BEA)
            )

            config = make_config(tmpdir).pour(lecteur)

            self.assertEqual("bea", config.username)
            # Sous l'identifiant, pas sous le nom : renommer ne sépare pas des journées.
            self.assertEqual(pathlib.Path(tmpdir) / ID_BEA, config.output_dir)
            self.assertEqual("Profil B", config.profil)
            self.assertEqual(["b@example.com"], config.smtp_to)
            self.assertEqual("Bea", config.prenom)

    def test_pour_carries_the_security_regime_of_the_document(self):
        """Personnel comme la stack, donc lu dans le document de chacun, pas dans l'installation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installation = make_config(tmpdir)
            bea = Lecteur("bea", profil_depuis_dict({CLE_ID: ID_BEA, "profil": "B", "securite": "curieux"}))

            self.assertIs(Securite.EXPLOITANT, installation.securite)
            self.assertIs(Securite.CURIEUX, installation.pour(bea).securite)

    def test_applying_twice_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lecteur = Lecteur("bea", Profil("B", identifiant=ID_BEA))
            with self.assertRaises(ValueError):
                make_config(tmpdir).pour(lecteur).pour(lecteur)

    def test_a_reader_needs_an_identifier(self):
        with self.assertRaises(ValueError):
            Lecteur("bea", Profil("B"))


class EtiquettesTests(unittest.TestCase):
    def test_tags_are_prefixed_by_the_username(self):
        tags = Etiquettes("adrien")

        self.assertEqual("adrien-score-07", tags.score(7))
        self.assertEqual("adrien-scoring-abc", tags.scoring("abc"))
        self.assertEqual("adrien-theme-cyber", tags.theme("cyber"))
        self.assertEqual("adrien-digested", tags.digest)

    def test_only_the_own_tags_are_read_back(self):
        """Ni les anciens tags sans préfixe — d'où un re-scoring unique — ni ceux d'un autre."""
        tags = Etiquettes("adrien")
        portes = ("score-09", "scoring-abc", "theme-cyber", "bea-score-03", "bea-scoring-def")

        self.assertIsNone(tags.score_de(portes))
        self.assertIsNone(tags.empreinte_de(portes))
        self.assertIsNone(tags.theme_de(portes))

        portes += ("adrien-score-08", "adrien-scoring-123", "adrien-theme-stack")
        self.assertEqual(8, tags.score_de(portes))
        self.assertEqual("123", tags.empreinte_de(portes))
        self.assertEqual("stack", tags.theme_de(portes))

    def test_a_name_that_extends_another_does_not_collide(self):
        self.assertIsNone(Etiquettes("adrien").score_de(("adrien-score-score-07",)))


def posts(client, action):
    with mock.patch.object(FreshRSSClient, "_ensure_edit_token", return_value="t"):
        with mock.patch.object(FreshRSSClient, "_post_form") as post_form:
            action(client)
    return [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]


class ClientParProfilTests(unittest.TestCase):
    def _client(self, tmpdir, username):
        config = make_config(tmpdir).pour(Lecteur(username, Profil("P", identifiant=nouvel_id())))
        return FreshRSSClient(config)

    def test_the_client_tags_under_the_profile_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._client(tmpdir, "adrien")

            labels = posts(client, lambda c: c.tag_notes({"item-1": Note(9, "cyber")}, "abc"))
            labels += posts(client, lambda c: c.mark_digested(["item-1"]))

        self.assertEqual(
            [
                ("a", f"{LABEL_STREAM_PREFIX}adrien-score-09"),
                ("a", f"{LABEL_STREAM_PREFIX}adrien-theme-cyber"),
                ("a", f"{LABEL_STREAM_PREFIX}adrien-scoring-abc"),
                ("a", f"{LABEL_STREAM_PREFIX}adrien-digested"),
            ],
            labels,
        )

    def test_clearing_leaves_the_tags_of_other_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = self._client(tmpdir, "adrien")
            porte = article("item-1", tags=("adrien-score-02", "bea-score-09", "score-05"))

            labels = posts(client, lambda c: c.clear_scoring_tags([porte]))

        self.assertEqual([("r", f"{LABEL_STREAM_PREFIX}adrien-score-02")], labels)

    def test_a_derived_client_shares_the_readings_but_not_the_prefix(self):
        """Une tournée lit chaque catégorie une fois, quel que soit le nombre de profils."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = FreshRSSClient(make_config(tmpdir))
            appels = []

            def _json_get(self, path, params=None):
                appels.append(path)
                if path.endswith("subscription/list"):
                    return {"subscriptions": [{"categories": [{"id": "user/-/label/Tech", "label": "Tech"}]}]}
                return {"items": []}

            adrien, bea = base.pour("adrien"), base.pour("bea")
            with mock.patch.object(FreshRSSClient, "_json_get", _json_get):
                for client in (adrien, bea):
                    client.list_categories()
                    client.fetch_daily_articles("Tech", JOUR)

            self.assertEqual(2, len(appels))
            self.assertEqual("adrien-digested", adrien.etiquettes.digest)
            self.assertEqual("bea-digested", bea.etiquettes.digest)


class FreshRSSQuiOublieLesLus(FakeFreshRSSClient):
    """Comme le vrai : un article marqué lu n'est plus rendu par la lecture du jour."""

    def __init__(self, articles_by_category):
        super().__init__(articles_by_category)
        self.appels_marquage = 0

    def fetch_daily_articles(self, category, day):
        lus = {a.item_id for a in self.marked_as_read}
        return [a for a in super().fetch_daily_articles(category, day) if a.item_id not in lus]

    def mark_as_read(self, articles):
        self.appels_marquage += 1
        super().mark_as_read(articles)

    def pour(self, username):
        return self


class TourneeTests(unittest.TestCase):
    def _annuaire(self, tmpdir, documents):
        dossier = pathlib.Path(tmpdir) / "profils"
        dossier.mkdir()
        for nom, document in documents.items():
            ecrire(dossier, f"{nom}.json", document)
        return AnnuaireDossier(dossier)

    def _tournee(self, tmpdir, documents, echoue=()):
        """Une tournée sur trois articles ; les profils de `echoue` lèvent à l'assemblage."""
        client = FreshRSSQuiOublieLesLus(
            {"Tech": [article("item-1"), article("item-2")], "News": [article("item-3")]}
        )
        vus: dict[str, list[str]] = {}

        def assembleur(config, freshrss):
            if config.username in echoue:
                raise RuntimeError("fournisseur en panne")

            class Espion(DigestService):
                def run(service, day, **kwargs):
                    digests = DigestService.run(service, day, **kwargs)
                    vus[config.username] = [a.item_id for d in digests for a in d.articles]
                    return digests

            return Espion(
                config=config,
                freshrss_client=freshrss.pour(config.username),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

        config = make_config(pathlib.Path(tmpdir) / "output")
        tournee = Tournee(config, self._annuaire(tmpdir, documents), client, assembleur)
        return tournee, client, vus

    DEUX = {"adrien": {"profil": "A"}, "bea": {"profil": "B"}}

    def test_every_profile_sees_the_whole_day_and_reading_is_marked_once_at_the_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, vus = self._tournee(tmpdir, self.DEUX)

            echecs = tournee.run(JOUR, send_email=False)

            self.assertEqual([], echecs)
            attendus = ["item-1", "item-2", "item-3"]
            self.assertEqual({"adrien": attendus, "bea": attendus}, vus)
            self.assertEqual(1, client.appels_marquage)
            self.assertEqual(attendus, sorted(a.item_id for a in client.marked_as_read))

    def test_each_profile_writes_under_its_own_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, _, _ = self._tournee(tmpdir, self.DEUX)

            tournee.run(JOUR, send_email=False)

            for nom in ("adrien", "bea"):
                # L'identifiant a été généré au premier passage, et écrit dans le document.
                document = pathlib.Path(tmpdir) / "profils" / f"{nom}.json"
                identifiant = json.loads(document.read_text(encoding="utf-8"))[CLE_ID]
                self.assertTrue(
                    (pathlib.Path(tmpdir) / "output" / identifiant / JOUR.isoformat()).is_dir()
                )

    def test_two_profiles_sharing_an_id_are_both_skipped(self):
        """Ils écriraient dans le même répertoire : aucun des deux n'est servi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            documents = {
                "adrien": {CLE_ID: ID_BEA, "profil": "A"},
                "bea": {CLE_ID: ID_BEA, "profil": "B"},
                "carl": {"profil": "C"},
            }
            tournee, client, vus = self._tournee(tmpdir, documents)

            self.assertEqual(["adrien", "bea"], tournee.run(JOUR, send_email=False))
            self.assertEqual(["carl"], list(vus))
            self.assertEqual(0, client.appels_marquage)

    def test_a_plain_text_document_fails_only_its_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, _, vus = self._tournee(
                tmpdir, {"adrien": "Un profil en texte brut", "bea": {"profil": "B"}}
            )

            self.assertEqual(["adrien"], tournee.run(JOUR, send_email=False))
            self.assertEqual(["bea"], list(vus))

    def test_a_failing_profile_does_not_stop_the_next_one_and_nothing_is_marked(self):
        """Le profil en échec doit pouvoir rejouer sa journée sans `--include-read`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, vus = self._tournee(tmpdir, self.DEUX, echoue=("adrien",))

            echecs = tournee.run(JOUR, send_email=False)

            self.assertEqual(["adrien"], echecs)
            self.assertIn("bea", vus)
            self.assertEqual(0, client.appels_marquage)

    def test_a_faulty_document_is_an_isolated_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, _, vus = self._tournee(
                tmpdir, {"adrien": '{"profil": ', "bea": {"profil": "B"}}
            )

            self.assertEqual(["adrien"], tournee.run(JOUR, send_email=False))
            self.assertIn("bea", vus)

    def test_a_targeted_run_does_not_mark_while_other_profiles_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, vus = self._tournee(tmpdir, self.DEUX)

            tournee.run(JOUR, "bea", send_email=False)

            self.assertEqual(["bea"], list(vus))
            self.assertEqual(0, client.appels_marquage)

    def test_a_targeted_run_marks_when_it_is_the_only_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, _ = self._tournee(tmpdir, {"adrien": {"profil": "A"}})

            tournee.run(JOUR, "adrien", send_email=False)

            self.assertEqual(1, client.appels_marquage)

    def test_no_mark_read_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, _ = self._tournee(tmpdir, self.DEUX)

            tournee.run(JOUR, send_email=False, mark_read=False)

            self.assertEqual(0, client.appels_marquage)

    def test_a_badly_named_file_does_not_stop_the_others_nor_the_marking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            documents = {**self.DEUX, "Jean Paul": {"profil": "J"}}
            tournee, client, vus = self._tournee(tmpdir, documents)

            with mock.patch("rssresume.profil.console.error"):
                self.assertEqual([], tournee.run(JOUR, send_email=False))

            self.assertEqual(["adrien", "bea"], sorted(vus))
            self.assertEqual(1, client.appels_marquage)

    def test_an_empty_directory_serves_nobody_without_failing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client, vus = self._tournee(tmpdir, {})

            self.assertEqual([], tournee.run(JOUR, send_email=False))
            self.assertEqual({}, vus)
            self.assertEqual(0, client.appels_marquage)


if __name__ == "__main__":
    unittest.main()
