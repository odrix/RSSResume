"""L'envoi par l'API de Resend, et le choix du transport.

Rien ne sort de la machine : `urlopen` est doublé, et ce que les tests jugent est la
requête qu'on lui a tendue — l'URL, l'en-tête d'autorisation, et le corps JSON.
"""

import base64
import json
import pathlib
import tempfile
import unittest
import urllib.error
from unittest import mock

from rssresume.config import MAIL_TRANSPORT_RESEND, MAIL_TRANSPORT_SMTP, AppConfig
from rssresume.external import mail, mailer_resend
from rssresume.external.mailer import EmailSender
from rssresume.external.mailer_resend import ResendEmailSender
from support import make_config


def config_resend(tmpdir, **surcharges):
    base = make_config(tmpdir).__dict__
    return AppConfig(
        **{
            **base,
            "mail_transport": MAIL_TRANSPORT_RESEND,
            "resend_api_key": "re_cle",
            **surcharges,
        }
    )


class FakeResponse:
    """Le contexte que rend `urlopen`, réduit à ce que le code en lit."""

    def __init__(self, corps=b'{"id": "msg-1"}'):
        self._corps = corps

    def read(self):
        return self._corps

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ResendEmailSenderTests(unittest.TestCase):
    def test_the_key_is_what_makes_it_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(ResendEmailSender(config_resend(tmpdir)).is_configured())
            self.assertFalse(
                ResendEmailSender(config_resend(tmpdir, resend_api_key=None)).is_configured()
            )

    def test_sending_without_a_key_raises_rather_than_posting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            expediteur = ResendEmailSender(config_resend(tmpdir, resend_api_key=None))
            with mock.patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(RuntimeError):
                    expediteur.send("Sujet", "Corps", [])

            urlopen.assert_not_called()

    def test_the_request_carries_the_key_and_the_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = config_resend(tmpdir)
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                ResendEmailSender(config).send("Résumé RSS", "Le corps", [])

            requete = urlopen.call_args.args[0]
            self.assertEqual(mailer_resend.API_URL, requete.full_url)
            self.assertEqual("Bearer re_cle", requete.get_header("Authorization"))
            envoye = json.loads(requete.data)
            self.assertEqual(config.smtp_from, envoye["from"])
            self.assertEqual(config.smtp_to, envoye["to"])
            self.assertEqual("Résumé RSS", envoye["subject"])
            self.assertEqual("Le corps", envoye["text"])
            # Pas de clé « attachments » vide : Resend n'a rien à en faire.
            self.assertNotIn("attachments", envoye)

    def test_an_attachment_travels_in_base64_with_its_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio = pathlib.Path(tmpdir) / "tech.mp3"
            audio.write_bytes(b"\x00\x01 son")
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                ResendEmailSender(config_resend(tmpdir)).send("Sujet", "Corps", [audio])

            piece = json.loads(urlopen.call_args.args[0].data)["attachments"][0]
            self.assertEqual("tech.mp3", piece["filename"])
            self.assertEqual(b"\x00\x01 son", base64.b64decode(piece["content"]))
            self.assertEqual("audio/mpeg", piece["content_type"])

    def test_an_http_error_says_what_resend_answered(self):
        """Un 403 nu ne dit rien ; le corps de la réponse nomme le domaine non vérifié."""
        refus = urllib.error.HTTPError(
            mailer_resend.API_URL, 403, "Forbidden", {}, None
        )
        refus.read = lambda: b'{"message": "domain is not verified"}'
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("urllib.request.urlopen", side_effect=refus):
                with self.assertRaises(RuntimeError) as raised:
                    ResendEmailSender(config_resend(tmpdir)).send("Sujet", "Corps", [])

            self.assertIn("403", str(raised.exception))
            self.assertIn("domain is not verified", str(raised.exception))

    def test_a_message_above_the_ceiling_never_leaves(self):
        """Monter quarante mégaoctets pour se faire refuser coûte la montée entière."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(mailer_resend, "MAX_PAYLOAD_BYTES", 10):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    with self.assertRaises(RuntimeError) as raised:
                        ResendEmailSender(config_resend(tmpdir)).send("Sujet", "Corps", [])

            urlopen.assert_not_called()
            self.assertIn("plafond", str(raised.exception))

    def test_an_opaque_answer_is_not_a_failure(self):
        """L'identifiant du message est un confort de log, pas un accusé de réception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"")):
                ResendEmailSender(config_resend(tmpdir)).send("Sujet", "Corps", [])


class TransportChoiceTests(unittest.TestCase):
    def test_smtp_is_what_the_default_config_builds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)

            self.assertEqual(MAIL_TRANSPORT_SMTP, config.mail_transport)
            self.assertIsInstance(mail.sender(config), EmailSender)

    def test_resend_is_what_the_flag_builds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsInstance(mail.sender(config_resend(tmpdir)), ResendEmailSender)


if __name__ == "__main__":
    unittest.main()
