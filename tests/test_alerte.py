"""L'alerte à l'exploitant en fin de tournée en échec, et qui la décide.

Ce que ces tests protègent :

- un profil en échec ne s'est plus dit seulement dans les logs : un seul email part à
  l'exploitant, qui nomme le profil, sa cause et le rejeu à lancer ;
- l'alerte ne coûte rien à la tournée : sans échec, sans adresse, sans transport configuré,
  ou l'échec d'elle-même, ni le service ni le marquage ne changent ;
- le filtrage `--dry-run` / `--no-email` vit dans `cli.main`, seul endroit qui connaît les
  drapeaux, la tournée reçoit le collaborateur, ou pas de collaborateur du tout.
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
from unittest import mock

from rssresume import cli
from rssresume.alerte import AlerteEchecs
from rssresume.digest import DigestService
from rssresume.models import EchecProfil
from rssresume.summaries import SummaryGenerator
from rssresume.tournee import Tournee
from tests.support import FakeAudioGenerator, FakeEmailSender, make_config
from tests.test_multiprofil import AnnuaireDossierCatalogue, FreshRSSQuiOublieLesLus, article, catalogue_public

JOUR = dt.date(2026, 8, 23)
#: L'adresse de l'exploitant des installations de ces tests.
ADMIN = "exploitant@example.com"
PROFIL = "adrien"


class ExpediteurQuiLeve:
    """Un transport qui lève au moment d'envoyer : le SMTP est mort, le DNS vanne."""

    def __init__(self):
        self.messages = []

    def is_configured(self):
        return True

    def send(self, subject, body, attachments, html=None, desabonnement=None):
        raise RuntimeError("SMTP injoignable")


class TourneeAlerteTests(unittest.TestCase):
    """Ce que `Tournee` demande à l'alerte qu'on lui a injectée."""

    DEUX = {"adrien": {"profil": "A"}, "bea": {"profil": "B"}}

    def _tournee(self, tmpdir, alerte, echoue=()):
        dossier = pathlib.Path(tmpdir) / "profils"
        dossier.mkdir()
        for nom in self.DEUX:
            (dossier / f"{nom}.json").write_text(
                json.dumps({"profil": f"Profil de {nom}"}), encoding="utf-8"
            )
        annuaire = AnnuaireDossierCatalogue(dossier, catalogue_public("Tech", "News"))
        client = FreshRSSQuiOublieLesLus(
            {"Tech": [article("item-1")], "News": [article("item-2")]}
        )

        def assembleur(config, freshrss):
            if config.username in echoue:
                raise RuntimeError("fournisseur en panne")
            return DigestService(
                config=config,
                freshrss_client=freshrss.pour(config.username),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

        config = make_config(pathlib.Path(tmpdir) / "output")
        return Tournee(config, annuaire, client, assembleur, alerte=alerte), client

    def test_a_failing_run_sends_one_email_naming_the_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expediteur = FakeEmailSender()
            tournee, _ = self._tournee(tmpdir, AlerteEchecs(expediteur), echoue=("adrien",))

            echecs = tournee.run(JOUR)

            self.assertEqual(["adrien"], echecs)
            (sujet, corps, pieces, html), = expediteur.messages
            self.assertEqual([], pieces)
            self.assertIsNone(html)
            self.assertIn("1 profil(s) en échec", sujet)
            self.assertIn("adrien", corps)
            self.assertIn("fournisseur en panne", corps)
            self.assertIn(f"--journal --date {JOUR.isoformat()} --profil adrien", corps)
            # Ce que l'un a échoué ne tache pas les autres : bea a été servi.
            self.assertNotIn("bea", corps)

    def test_a_clean_run_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expediteur = FakeEmailSender()
            tournee, client = self._tournee(tmpdir, AlerteEchecs(expediteur))

            echecs = tournee.run(JOUR)

            self.assertEqual([], echecs)
            self.assertEqual([], expediteur.messages)
            self.assertEqual(1, client.appels_marquage)

    def test_two_failed_profiles_get_one_email_with_both_names(self):
        """Deux échecs, un seul email : les deux profils nommés, chacun avec son rejeu."""
        with tempfile.TemporaryDirectory() as tmpdir:
            expediteur = FakeEmailSender()
            tournee, _ = self._tournee(
                tmpdir, AlerteEchecs(expediteur), echoue=("adrien", "bea")
            )

            echecs = tournee.run(JOUR)

            self.assertEqual(["adrien", "bea"], echecs)
            (sujet, corps, _, _), = expediteur.messages
            self.assertIn("2 profil(s) en échec", sujet)
            self.assertIn("adrien", corps)
            self.assertIn("bea", corps)
            self.assertIn("--profil adrien", corps)
            self.assertIn("--profil bea", corps)

    def test_a_failed_alert_neither_stops_the_run_nor_the_marking(self):
        """Un SMTP mort au pire moment ne doit pas transformer une tournée finie en échec.

        Un profil en échec diffère déjà le marquage par construction, c'est la règle
        d'isolement de la tournée : le test vérifie que la décision de marquage est prise
        comme avant, l'échec de l'alerte laissant le rendu des échecs intact.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tournee, client = self._tournee(
                tmpdir, AlerteEchecs(ExpediteurQuiLeve()), echoue=("adrien",)
            )

            with mock.patch("rssresume.tournee.console.log") as log, \
                    mock.patch("rssresume.tournee.console.error") as erreur:
                echecs = tournee.run(JOUR)

            self.assertEqual(["adrien"], echecs)
            erreurs = [appel.args[0] for appel in erreur.call_args_list]
            self.assertTrue(any("Alerte à l'exploitant impossible" in m for m in erreurs))
            # La décision de marquage a bien été prise, différée, un profil doit
            # rejouer sa journée, et non court-circuitée par l'erreur d'alerte.
            logs = [appel.args[0] for appel in log.call_args_list]
            self.assertTrue(any("Marquage comme lu : différé" in m for m in logs))
            self.assertEqual(0, client.appels_marquage)


class AlerteSeuleTests(unittest.TestCase):
    """`AlerteEchecs` seule : le transport, pas la tournée."""

    def test_an_unconfigured_transport_logs_and_sends_nothing(self):
        """Pas de courrier configuré, l'alerte est un silence : ni levée, ni envoi."""
        expediteur = FakeEmailSender()

        class SansTransport(FakeEmailSender):
            def is_configured(self):
                return False

        alerte = AlerteEchecs(SansTransport())

        with mock.patch("rssresume.alerte.console.error") as erreur:
            alerte.notifier(JOUR, [EchecProfil(PROFIL, "RuntimeError('fournisseur en panne')")])

        self.assertEqual([], expediteur.messages)
        self.assertTrue(erreur.called)
        self.assertIn(PROFIL, erreur.call_args.args[0])


class ChoixDuCLITests(unittest.TestCase):
    """Le seul endroit qui connaît les drapeaux décide si la tournée aura une alerte."""

    def _main(self, tmpdir, *options, admin_email=ADMIN):
        config = dataclasses.replace(make_config(tmpdir), admin_email=admin_email)
        dossier = pathlib.Path(tmpdir) / "profils"
        dossier.mkdir(exist_ok=True)
        (dossier / f"{PROFIL}.json").write_text(json.dumps({"profil": "A"}), encoding="utf-8")
        env = {"ENV_PROFILES_DIR": str(dossier), "RSSRESUME_PROFILES_DIR": str(dossier)}
        sortie = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(cli.AppConfig, "from_env", return_value=config):
            with mock.patch.object(cli, "build_service"), \
                    mock.patch.object(cli, "Tournee") as tournee:
                with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
                    cli.main([*options, "--date", JOUR.isoformat()])
        return tournee.call_args

    def test_dry_run_sends_nothing(self):
        """Ni `--dry-run` ni `--no-email` : la tournée tourne sans collaborateur d'alerte."""
        with tempfile.TemporaryDirectory() as tmpdir:
            avec_courrier = self._main(tmpdir)
            self.assertIsInstance(avec_courrier.kwargs["alerte"], AlerteEchecs)

        for options in (["--dry-run"], ["--no-email"]):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as tmpdir:
                appel = self._main(tmpdir, *options)
                self.assertIsNone(appel.kwargs["alerte"])


if __name__ == "__main__":
    unittest.main()
