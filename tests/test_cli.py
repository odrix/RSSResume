"""Ce que la ligne de commande décide avant que le service soit assemblé.

Ce que ces tests protègent :

- `--audio-mode` doit l'emporter sur l'environnement sans jamais devenir le défaut. Un
  défaut posé dans `argparse` écraserait `RSSRESUME_AUDIO_MODE` à chaque passage du
  conteneur, en silence — et le mode décide combien de fichiers audio la journée produit ;
- `--journal` doit court-circuiter l'assemblage. C'est la commande qui sert quand quelque
  chose ne va pas : exiger d'elle un fournisseur la ferait tomber pour la même raison que
  ce qu'on cherche à diagnostiquer.
"""

import contextlib
import dataclasses
import datetime as dt
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import cli, runlog
from rssresume.config import AUDIO_MODE_CATEGORY, AUDIO_MODE_GLOBAL
from rssresume.tools import console
from tests.support import make_config

JOUR = dt.date(2026, 8, 30)


def mode_retenu(mode_environnement, options=()):
    """Le mode que `main` a réellement remis au service, l'option ayant eu son mot à dire."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = dataclasses.replace(make_config(tmpdir), audio_mode=mode_environnement)
        with mock.patch.object(cli.AppConfig, "from_env", return_value=config):
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


def journee_produite(racine):
    """Une journée sur le disque, réduite à ce que le bilan a besoin de lire."""
    day_dir = pathlib.Path(racine) / JOUR.isoformat()
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


def lance(argv, racine, debug_env=False):
    """Exécute `main` sur une configuration de test ; renvoie (code, sortie console)."""
    config = dataclasses.replace(
        make_config(racine), output_dir=pathlib.Path(racine), debug=debug_env
    )
    sortie = io.StringIO()
    with mock.patch.object(cli.AppConfig, "from_env", return_value=config):
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


if __name__ == "__main__":
    unittest.main()
