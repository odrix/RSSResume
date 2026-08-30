"""Le renvoi de l'email d'une journée déjà produite, depuis ses journaux.

Ce que ces tests protègent tient en une phrase : une journée coûte cher, et l'envoi seul
peut échouer longtemps après qu'elle est payée.
"""

import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import cli, runlog
from rssresume.config import AppConfig
from support import make_config

JOUR = dt.date(2026, 8, 29)


class FakeSender:
    def __init__(self, configured=True):
        self._configured = configured
        self.envois = []

    def is_configured(self):
        return self._configured

    def send(self, subject, body, attachments):
        self.envois.append({"subject": subject, "body": body, "attachments": list(attachments)})


def ecrire_journee(racine, avec_audio=True, resume="Le résumé de Tech."):
    """Une journée sur le disque, telle que `runlog` l'écrit."""
    day_dir = pathlib.Path(racine) / JOUR.isoformat()
    day_dir.mkdir(parents=True)
    if avec_audio:
        (day_dir / "1-tech.mp3").write_bytes(b"son")
    journal = {
        "categorie": "1 - Tech",
        "date": JOUR.isoformat(),
        "resume": resume,
        "resultat": {"statut": "audio", "audio": "1-tech.mp3" if avec_audio else None},
        "articles": [
            {
                "item_id": "b",
                "titre": "Second",
                "flux": "Flux B",
                "url": "https://exemple.test/b",
                "publie_le": "2026-08-29T09:00:00+02:00",
                "retenu": True,
                "rang_digest": 2,
            },
            {
                "item_id": "a",
                "titre": "Premier",
                "flux": "Flux A",
                "url": "https://exemple.test/a",
                "publie_le": None,
                "retenu": True,
                "rang_digest": 1,
            },
            {"item_id": "c", "titre": "Écarté", "url": "https://exemple.test/c", "retenu": False},
        ],
    }
    (day_dir / "1-tech.log.json").write_text(
        json.dumps(journal, ensure_ascii=False), encoding="utf-8"
    )
    return day_dir


class ReadDayTests(unittest.TestCase):
    def test_a_day_is_rebuilt_from_its_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            day_dir = ecrire_journee(tmpdir)

            digest, = runlog.read_day(day_dir)

            self.assertEqual("1 - Tech", digest.category)
            self.assertEqual("Le résumé de Tech.", digest.summary_text)
            self.assertEqual(day_dir / "1-tech.mp3", digest.audio_path)

    def test_only_the_selected_articles_come_back_in_digest_order(self):
        """L'ordre du digest, pas celui du journal : le journal classe par score."""
        with tempfile.TemporaryDirectory() as tmpdir:
            digest, = runlog.read_day(ecrire_journee(tmpdir))

            self.assertEqual(["Premier", "Second"], [link.title for link in digest.links])
            self.assertEqual(["Flux A", "Flux B"], [link.source for link in digest.links])

    def test_an_audio_deleted_since_does_not_break_the_replay(self):
        """Le journal nomme un fichier ; rien ne garantit qu'il soit encore là."""
        with tempfile.TemporaryDirectory() as tmpdir:
            day_dir = ecrire_journee(tmpdir)
            (day_dir / "1-tech.mp3").unlink()

            digest, = runlog.read_day(day_dir)

            self.assertIsNone(digest.audio_path)

    def test_a_missing_day_is_empty_rather_than_an_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual([], runlog.read_day(pathlib.Path(tmpdir) / "2026-01-01"))

    def test_a_log_written_before_the_summary_was_kept_is_still_readable(self):
        """Les journées d'avant ce champ se relisent, sans le texte du résumé."""
        with tempfile.TemporaryDirectory() as tmpdir:
            day_dir = ecrire_journee(tmpdir)
            chemin = day_dir / "1-tech.log.json"
            ancien = json.loads(chemin.read_text(encoding="utf-8"))
            del ancien["resume"]
            chemin.write_text(json.dumps(ancien, ensure_ascii=False), encoding="utf-8")

            digest, = runlog.read_day(day_dir)

            self.assertEqual("", digest.summary_text)
            self.assertEqual(2, len(digest.links))


class SendOnlyTests(unittest.TestCase):
    def test_the_email_carries_the_summary_the_links_and_the_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            day_dir = ecrire_journee(tmpdir)
            config = AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})
            sender = FakeSender()

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                code = cli.send_only(config, JOUR)

            self.assertEqual(0, code)
            envoi, = sender.envois
            self.assertIn(JOUR.isoformat(), envoi["subject"])
            self.assertIn("Le résumé de Tech.", envoi["body"])
            self.assertIn("https://exemple.test/a", envoi["body"])
            self.assertNotIn("https://exemple.test/c", envoi["body"])
            self.assertEqual([day_dir / "1-tech.mp3"], envoi["attachments"])

    def test_a_day_without_logs_sends_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})
            sender = FakeSender()

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                code = cli.send_only(config, JOUR)

            self.assertEqual(1, code)
            self.assertEqual([], sender.envois)

    def test_an_incomplete_configuration_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire_journee(tmpdir)
            config = AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})
            sender = FakeSender(configured=False)

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                code = cli.send_only(config, JOUR)

            self.assertEqual(1, code)
            self.assertEqual([], sender.envois)


class SendOnlyArgumentsTests(unittest.TestCase):
    """Le renvoi court-circuite l'assemblage : aucun fournisseur n'est construit."""

    def test_send_only_never_builds_the_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})
            ecrire_journee(tmpdir)
            with mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(cli, "build_service") as build:
                    with mock.patch.object(cli.mail, "sender", return_value=FakeSender()):
                        code = cli.main(["--send-only", "--date", JOUR.isoformat()])

            self.assertEqual(0, code)
            build.assert_not_called()

    def test_send_only_refuses_the_flags_that_contradict_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})
            with mock.patch.object(cli.AppConfig, "from_env", return_value=config):
                with mock.patch.object(cli, "send_only") as renvoi:
                    code = cli.main(["--send-only", "--no-email", "--date", JOUR.isoformat()])

            self.assertEqual(2, code)
            renvoi.assert_not_called()


if __name__ == "__main__":
    unittest.main()
