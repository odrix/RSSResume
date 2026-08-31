"""Ce que la ligne de commande décide avant que le service soit assemblé.

Ce que ces tests protègent : `--audio-mode` doit l'emporter sur l'environnement sans
jamais devenir le défaut. Un défaut posé dans `argparse` écraserait
`RSSRESUME_AUDIO_MODE` à chaque passage du conteneur, en silence — et le mode décide
combien de fichiers audio la journée produit.
"""

import contextlib
import dataclasses
import datetime as dt
import io
import tempfile
import unittest
from unittest import mock

from rssresume import cli
from rssresume.config import AUDIO_MODE_CATEGORY, AUDIO_MODE_GLOBAL
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


if __name__ == "__main__":
    unittest.main()
