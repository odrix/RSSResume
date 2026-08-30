"""Le journal de la journée : l'éphéméride écrite une fois, relue au renvoi.

Ce que ces tests protègent : `--send-only` doit renvoyer le MÊME email que l'original.
Sans ce fichier, il faudrait soit repayer l'appel du modèle, soit ouvrir la lettre sur
une autre phrase que celle qui est partie la première fois.
"""

import datetime as dt
import json
import pathlib
import tempfile
import unittest
import zoneinfo
from unittest import mock

from rssresume import cli, runlog
from rssresume.ephemeride import fetes
from rssresume.config import AppConfig
from rssresume.models import Ephemeride
from rssresume.newsletter import date_longue
from tests.support import make_config
from tests.test_send_only import JOUR, FakeSender, ecrire_journee

#: Le jour où le renvoi a lieu : maintenant, dans le fuseau de la configuration. C'est
#: sur lui que la lettre renvoyée doit s'ouvrir, et non sur la journée qu'elle raconte.
AUJOURD_HUI = dt.datetime.now(zoneinfo.ZoneInfo("Europe/Paris")).date()


def ephem(texte="1988 — le ver Morris.", jour=JOUR, origine="llm"):
    return Ephemeride(jour=jour, fete=fetes.du_jour(jour), texte=texte, origine=origine)


class EcritureTests(unittest.TestCase):
    def test_a_model_written_ephemeride_is_kept(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine) as journal:
                journal.set_ephemeride(ephem())

            ecrit = json.loads((racine / runlog.DAY_LOG_NAME).read_text(encoding="utf-8"))
            self.assertEqual("1988 — le ver Morris.", ecrit["ephemeride"]["texte"])
            self.assertEqual("llm", ecrit["ephemeride"]["origine"])
            # Le jour décrit, pour que le renvoi sache si elle parle encore du bon.
            self.assertEqual(JOUR.isoformat(), ecrit["ephemeride"]["jour"])
            self.assertEqual("sainte Sabine", ecrit["ephemeride"]["fete"])

    def test_a_calendar_ephemeride_is_not_worth_a_file(self):
        """Elle se recalcule à l'identique de la seule date : l'écrire ne transporte rien."""
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine) as journal:
                journal.set_ephemeride(ephem("242e jour de l'année.", origine="calendrier"))

            self.assertFalse((racine / runlog.DAY_LOG_NAME).exists())

    def test_a_call_made_outside_any_category_lands_in_the_day_journal(self):
        """C'est la raison d'être du scope : cet appel n'était compté nulle part."""
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine):
                runlog.record_chat("ephemeride", "un-modele", {"prompt_tokens": 120, "completion_tokens": 40})

            ecrit = json.loads((racine / runlog.DAY_LOG_NAME).read_text(encoding="utf-8"))
            poste = ecrit["couts"]["par_typologie"]["ephemeride"]
            self.assertEqual(1, poste["appels"])
            self.assertEqual(120, poste["tokens_entree"])

    def test_a_category_scope_gives_the_day_journal_back(self):
        """Les catégories prennent la main chacune à leur tour, puis la rendent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine) as jour:
                with runlog.category_scope("Tech", "tech", JOUR, racine):
                    runlog.record_chat("digest", "un-modele", {"prompt_tokens": 10})
                runlog.record_chat("ephemeride", "un-modele", {"prompt_tokens": 5})

            self.assertEqual(["ephemeride"], [appel.label for appel in jour.calls])

    def test_the_day_journal_is_written_even_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with self.assertRaises(RuntimeError):
                with runlog.day_scope(JOUR, racine) as journal:
                    journal.set_ephemeride(ephem())
                    raise RuntimeError("la journée s'est arrêtée là")

            self.assertTrue((racine / runlog.DAY_LOG_NAME).exists())

    def test_the_day_journal_is_not_mistaken_for_a_category(self):
        """`read_day` ramasse les journaux au glob : celui-ci ne doit pas y répondre."""
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine) as journal:
                journal.set_ephemeride(ephem())

            self.assertEqual([], runlog.read_day(racine))


class RelectureTests(unittest.TestCase):
    def test_the_ephemeride_comes_back_as_it_was_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(JOUR, racine) as journal:
                journal.set_ephemeride(ephem())

            relue = runlog.read_ephemeride(racine)

            self.assertEqual("1988 — le ver Morris.", relue.texte)
            self.assertEqual("llm", relue.origine)
            self.assertEqual(JOUR, relue.jour)
            self.assertEqual("sainte Sabine", relue.fete)

    def test_a_day_without_a_journal_returns_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(runlog.read_ephemeride(pathlib.Path(tmpdir)))

    def test_an_unreadable_journal_returns_nothing_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            (racine / runlog.DAY_LOG_NAME).write_text("{ pas du JSON", encoding="utf-8")

            self.assertIsNone(runlog.read_ephemeride(racine))


class RenvoiTests(unittest.TestCase):
    """Le renvoi doit dire la même chose que l'original, sans rappeler personne."""

    @staticmethod
    def _config(tmpdir):
        return AppConfig(**{**make_config(tmpdir).__dict__, "output_dir": pathlib.Path(tmpdir)})

    @staticmethod
    def _ecrire_journal_de_jour(day_dir, jour):
        (day_dir / runlog.DAY_LOG_NAME).write_text(
            json.dumps(
                {
                    "date": JOUR.isoformat(),
                    "ephemeride": {
                        "jour": jour.isoformat(),
                        "fete": fetes.du_jour(jour),
                        "texte": "1988 — le ver Morris.",
                        "origine": "llm",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_resending_the_same_day_reuses_the_ephemeride_already_paid_for(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._ecrire_journal_de_jour(ecrire_journee(tmpdir), AUJOURD_HUI)
            sender = FakeSender()

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                self.assertEqual(0, cli.send_only(self._config(tmpdir), JOUR))

            envoi, = sender.envois
            self.assertIn("1988 — le ver Morris.", envoi["body"])
            self.assertIn("1988 — le ver Morris.", envoi["html"])

    def test_resending_later_reopens_on_the_day_of_the_resend(self):
        """Une éphéméride d'un autre jour daterait la lettre et annoncerait la mauvaise fête."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vieux = AUJOURD_HUI - dt.timedelta(days=30)
            self._ecrire_journal_de_jour(ecrire_journee(tmpdir), vieux)
            sender = FakeSender()

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                self.assertEqual(0, cli.send_only(self._config(tmpdir), JOUR))

            envoi, = sender.envois
            self.assertNotIn("1988 — le ver Morris.", envoi["body"])
            self.assertIn(date_longue(AUJOURD_HUI).capitalize(), envoi["body"])

    def test_the_resent_letter_opens_on_today_not_on_the_day_it_covers(self):
        """C'est aujourd'hui que la lettre arrive : c'est la date que son lecteur attend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire_journee(tmpdir)
            sender = FakeSender()

            with mock.patch.object(cli.mail, "sender", return_value=sender):
                self.assertEqual(0, cli.send_only(self._config(tmpdir), JOUR))

            envoi, = sender.envois
            self.assertIn(date_longue(AUJOURD_HUI).capitalize(), envoi["body"])
            self.assertIn(fetes.du_jour(AUJOURD_HUI), envoi["body"])
            # Le titre, lui, nomme toujours la journée racontée.
            self.assertIn("29 août 2026", envoi["subject"])

    def test_resending_calls_no_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecrire_journee(tmpdir)
            sender = FakeSender()

            with mock.patch.object(cli.llm, "for_action") as fabrique:
                with mock.patch.object(cli.mail, "sender", return_value=sender):
                    self.assertEqual(0, cli.send_only(self._config(tmpdir), JOUR))

            fabrique.assert_not_called()


if __name__ == "__main__":
    unittest.main()
