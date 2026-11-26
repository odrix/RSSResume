"""Ce que la ligne de commande décide avant que le service soit assemblé.

Ce que ces tests protègent :

- `--audio-mode` doit l'emporter sur l'environnement sans jamais devenir le défaut. Un
  défaut posé dans `argparse` écraserait `RSSRESUME_AUDIO_MODE` à chaque passage du
  conteneur, en silence, et le mode décide combien de fichiers audio la journée produit ;
- `--journal` doit court-circuiter l'assemblage. C'est la commande qui sert quand quelque
  chose ne va pas : exiger d'elle un fournisseur la ferait tomber pour la même raison que
  ce qu'on cherche à diagnostiquer.
"""

import contextlib
import dataclasses
import datetime as dt
import io
import json
import os
import pathlib
import tempfile
import unittest
import uuid
from unittest import mock

from rssresume import cli, runlog
from rssresume.config import AUDIO_MODE_CATEGORY, AUDIO_MODE_GLOBAL
from rssresume.profil import ENV_PROFIL, ENV_PROFILES_DIR, AnnuaireDossier
from rssresume.tools import console
from tests.support import make_config
from tests.test_multiprofil import catalogue_public

JOUR = dt.date(2026, 8, 30)
#: La personne servie par défaut dans ces tests : sans profil déclaré, rien ne tourne.
PROFIL = "adrien"


def id_de(nom):
    """Un identifiant stable par nom : la sortie d'un profil est rangée sous lui."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, nom))


def dossier_profils(racine, *noms):
    """Un dossier de profils sous `racine`, un document par nom ; rend l'environnement."""
    dossier = pathlib.Path(racine) / "profils"
    dossier.mkdir(exist_ok=True)
    for nom in noms:
        (dossier / f"{nom}.json").write_text(
            json.dumps(
                {"id": id_de(nom), "profil": f"Profil de {nom}", "email": f"{nom}@example.com"}
            ),
            encoding="utf-8",
        )
    return {ENV_PROFILES_DIR: str(dossier)}


def mode_retenu(mode_environnement, options=()):
    """Le mode que `main` a réellement remis au service, l'option ayant eu son mot à dire."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = dataclasses.replace(make_config(tmpdir), audio_mode=mode_environnement)
        env = dossier_profils(tmpdir, PROFIL)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(cli.AppConfig, "from_env", return_value=config):
            with mock.patch.object(cli, "build_service") as build:
                cli.main([*options, "--date", JOUR.isoformat(), "--dry-run"])
        return build.call_args.args[0].audio_mode


class AudioModeOptionTests(unittest.TestCase):
    def test_without_the_option_the_environment_decides(self):
        self.assertEqual(AUDIO_MODE_GLOBAL, mode_retenu(AUDIO_MODE_GLOBAL))
        self.assertEqual(AUDIO_MODE_CATEGORY, mode_retenu(AUDIO_MODE_CATEGORY))

    def test_the_option_wins_over_the_environment(self):
        """Essayer l'autre mode sur une journée sans toucher au `.env` du conteneur."""
        self.assertEqual(
            AUDIO_MODE_GLOBAL,
            mode_retenu(AUDIO_MODE_CATEGORY, ["--audio-mode", AUDIO_MODE_GLOBAL]),
        )
        self.assertEqual(
            AUDIO_MODE_CATEGORY,
            mode_retenu(AUDIO_MODE_GLOBAL, ["--audio-mode", AUDIO_MODE_CATEGORY]),
        )

    def test_an_unknown_mode_is_refused_by_the_parser(self):
        # `argparse` écrit son mode d'emploi sur la sortie d'erreur avant de sortir :
        # détourné ici, il n'a pas à salir le compte rendu de la suite.
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.parse_args(["--audio-mode", "journee"])


def journee_produite(racine, username=PROFIL):
    """Une journée sur le disque, réduite à ce que le bilan a besoin de lire.

    Sous le répertoire de la personne, nommé par son identifiant.
    """
    day_dir = pathlib.Path(racine) / id_de(username) / JOUR.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"2-cyber{runlog.LOG_SUFFIX}").write_text(
        json.dumps(
            {
                "categorie": "2 - Cyber",
                "resultat": {"statut": "audio", "articles": 3, "retenus": 1,
                             "seuil_applique": 7, "audio": "2-cyber.mp3"},
                "couts": {"total": 0.001, "appels": []},
                "articles": [{"titre": "Une faille dans Traefik", "score": 9,
                              "thematique": "cyber", "origine_note": "tags",
                              "retenu": True}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return day_dir


def lance(argv, racine, debug_env=False, env=None):
    """Exécute `main` sur une configuration de test ; renvoie (code, sortie console).

    L'environnement est remplacé, par `env`, sinon par un dossier qui ne déclare que
    `PROFIL`, pour que les profils servis ne dépendent pas du poste qui lance la suite.
    """
    config = dataclasses.replace(
        make_config(racine), output_dir=pathlib.Path(racine), debug=debug_env
    )
    if env is None:
        env = dossier_profils(racine, PROFIL)
    sortie = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(cli.AppConfig, "from_env", return_value=config):
        with mock.patch.object(cli, "build_service") as build:
            # Les deux sorties : `console.log` écrit sur la standard, `console.error` sur
            # l'erreur, et ni l'une ni l'autre n'a sa place dans le compte rendu de la suite.
            with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
                console.enable(True)
                try:
                    code = cli.main([*argv, "--date", JOUR.isoformat()])
                finally:
                    console.enable(False)
    return code, sortie.getvalue(), build


class CategoriesLimitOptionTests(unittest.TestCase):
    def test_categories_overrides_the_environment_selection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(tmpdir), categories=["News"])
            env = dossier_profils(tmpdir, PROFIL)
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(cli.FreshRSSClient, "list_categories", return_value=["Tech", "News"]):
                    with mock.patch.object(cli, "build_service") as build:
                        cli.main(["--categories", "Tech,News", "--date", JOUR.isoformat(), "--dry-run"])

            service_config = build.call_args.args[0]
            self.assertEqual(["Tech", "News"], service_config.categories_surcharge)

    def test_limit_is_passed_to_the_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            env = dossier_profils(tmpdir, PROFIL)
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(cli, "build_service") as build:
                    cli.main(["--limit", "3", "--date", JOUR.isoformat(), "--dry-run"])

            service_config = build.call_args.args[0]
            self.assertEqual(3, service_config.limite_articles)

    def test_unknown_category_is_reported_and_stops_the_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(tmpdir), categories=["Tech", "News"])
            env = dossier_profils(tmpdir, PROFIL)
            sortie = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(cli.FreshRSSClient, "list_categories", return_value=["Tech", "News"]):
                    with contextlib.redirect_stderr(sortie):
                        console.enable(True)
                        try:
                            code = cli.main(["--categories", "Tech,Introuvable", "--date", JOUR.isoformat(), "--dry-run"])
                        finally:
                            console.enable(False)

            self.assertEqual(2, code)
            self.assertIn("Introuvable", sortie.getvalue())
            self.assertIn("inconnue", sortie.getvalue())

    def test_categories_check_fails_explicitly_when_freshrss_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(tmpdir), categories=["Tech", "News"])
            env = dossier_profils(tmpdir, PROFIL)
            sortie = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(
                    cli.FreshRSSClient,
                    "list_categories",
                    side_effect=RuntimeError("FreshRSS injoignable"),
                ):
                    with contextlib.redirect_stderr(sortie):
                        console.enable(True)
                        try:
                            code = cli.main(["--categories", "Tech", "--date", JOUR.isoformat(), "--dry-run"])
                        finally:
                            console.enable(False)

            self.assertEqual(2, code)
            self.assertIn("impossible de vérifier --categories", sortie.getvalue())
            self.assertIn("FreshRSS injoignable", sortie.getvalue())

    def test_limit_must_be_a_positive_integer(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args(["--limit", "0"])


class JournalTests(unittest.TestCase):
    def test_the_journal_never_builds_the_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journee_produite(tmpdir)

            code, sortie, build = lance(["--journal"], tmpdir)

            self.assertEqual(0, code)
            build.assert_not_called()
            self.assertIn("2 - Cyber", sortie)

    def test_a_day_that_was_never_produced_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            code, _, _ = lance(["--journal"], tmpdir)

            self.assertEqual(1, code)

    def test_the_articles_appear_only_in_debug(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journee_produite(tmpdir)

            _, sobre, _ = lance(["--journal"], tmpdir)
            _, bavard, _ = lance(["--journal", "--debug"], tmpdir)

            self.assertNotIn("Traefik", sobre)
            self.assertIn("Traefik", bavard)

    def test_the_environment_can_turn_the_detail_on(self):
        """C'est par là que le conteneur l'active : il n'a pas de ligne de commande."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journee_produite(tmpdir)

            _, sortie, _ = lance(["--journal"], tmpdir, debug_env=True)

            self.assertIn("Traefik", sortie)


class DebugApresExecutionTests(unittest.TestCase):
    def test_a_normal_run_prints_the_report_when_debug_is_on(self):
        """Le but de l'exercice : le bilan atterrit dans la sortie standard, donc dans
        l'onglet Logs du conteneur, sans qu'on ait à aller chercher un fichier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journee_produite(tmpdir)

            code, sortie, build = lance([], tmpdir, debug_env=True)

            self.assertEqual(0, code)
            build.assert_called_once()
            self.assertIn("2 - Cyber", sortie)
            self.assertIn("Traefik", sortie)

    def test_a_normal_run_stays_quiet_without_debug(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journee_produite(tmpdir)

            _, sortie, _ = lance([], tmpdir)

            self.assertNotIn("2 - Cyber", sortie)


class ProfilOptionTests(unittest.TestCase):
    """`--profil` cible une personne ; sans lui, toutes. Les relectures suivent."""

    def _dossier(self, racine, *noms):
        return dossier_profils(racine, *noms)

    def _catalogue(self):
        """Un catalogue pour le dossier : sans lui, la tournée de deux profils refuse de
        démarrer, ce que ces tests ne jugent pas."""
        return mock.patch.object(
            AnnuaireDossier, "catalogue", return_value=catalogue_public("Tech", "News")
        )

    def test_nothing_declared_reads_and_builds_nothing(self):
        """Ni dossier ni document : pas d'action, pas de résumé."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(cli.FreshRSSClient, "list_categories") as lecture:
                code, sortie, build = lance([], tmpdir, env={})

            self.assertEqual(0, code)
            build.assert_not_called()
            lecture.assert_not_called()
            self.assertIn("aucun profil", sortie)

    def test_an_inline_profile_without_a_document_fails_at_launch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                lance([], tmpdir, env={ENV_PROFIL: "Un profil en ligne"})

    def test_the_journal_of_one_profile_is_read_under_its_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien", "bea")
            journee_produite(tmpdir, "bea")

            code, sortie, _ = lance(["--journal", "--profil", "bea"], tmpdir, env=env)

            self.assertEqual(0, code)
            self.assertIn("2 - Cyber", sortie)

    def test_without_the_option_every_profile_is_read_and_a_missing_one_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien", "bea")
            journee_produite(tmpdir, "bea")

            code, sortie, _ = lance(["--journal"], tmpdir, env=env)

            self.assertEqual(1, code)
            self.assertIn("adrien", sortie)
            self.assertIn("2 - Cyber", sortie)

    def test_an_unknown_profile_fails_before_anything(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien")

            with self.assertRaises(ValueError):
                lance(["--journal", "--profil", "inconnu"], tmpdir, env=env)

    def test_a_run_builds_one_service_per_profile_with_its_own_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien", "bea")

            with self._catalogue():
                code, _, build = lance(["--dry-run"], tmpdir, env=env)

            self.assertEqual(0, code)
            configs = [appel.args[0] for appel in build.call_args_list]
            self.assertEqual(["adrien", "bea"], [config.username for config in configs])
            self.assertEqual(pathlib.Path(tmpdir) / id_de("bea"), configs[1].output_dir)
            self.assertEqual(["bea@example.com"], configs[1].smtp_to)
            self.assertEqual("Profil de bea", configs[1].profil)

    def test_a_refused_catalogue_is_a_message_and_exit_code_2_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien", "bea")

            code, sortie, build = lance(["--dry-run"], tmpdir, env=env)

            self.assertEqual(2, code)
            self.assertIn("importer-catalogue", sortie)
            self.assertNotIn("Traceback", sortie)
            build.assert_not_called()

    def test_the_option_serves_only_that_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = self._dossier(tmpdir, "adrien", "bea")

            with self._catalogue():
                _, _, build = lance(["--dry-run", "--profil", "bea"], tmpdir, env=env)

            self.assertEqual(["bea"], [appel.args[0].username for appel in build.call_args_list])


if __name__ == "__main__":
    unittest.main()
