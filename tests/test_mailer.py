import email
import email.policy
import email.utils
import smtplib
import tempfile
import unittest
from unittest import mock

from rssresume.config import AppConfig
from rssresume.external import mailer
from rssresume.external.mailer import EmailSender
from tests.support import make_config


class EmailSenderTests(unittest.TestCase):
    def test_email_sender_detects_incomplete_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "smtp_host": None})

            self.assertFalse(EmailSender(config).is_configured())

    def test_email_sender_is_configured_with_host_from_and_recipients(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(EmailSender(make_config(tmpdir)).is_configured())

    def test_message_carries_date_and_message_id(self):
        """Sans ces deux en-têtes, le digest part et se range dans les indésirables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            message = EmailSender(config)._build_message("Sujet", "Corps", [])

            self.assertTrue(email.utils.parsedate_to_datetime(message["Date"]))
            self.assertRegex(message["Message-ID"], r"^<.+@.+>$")
            self.assertTrue(message["Message-ID"].endswith(config.smtp_from.split("@")[-1] + ">"))

    def test_the_unsubscribe_link_sets_the_one_click_headers(self):
        """Exigés par Gmail et Yahoo des expéditeurs en volume (RFC 8058)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            url = "https://veille.example.com/desabonnement/v1.abc.def"
            message = EmailSender(make_config(tmpdir))._build_message(
                "Sujet", "Corps", [], "<p>Corps</p>", desabonnement=url
            )

            self.assertEqual(f"<{url}>", message["List-Unsubscribe"])
            self.assertEqual("List-Unsubscribe=One-Click", message["List-Unsubscribe-Post"])

    def test_a_long_unsubscribe_link_leaves_in_clear_and_unfolded(self):
        """Plié à 78 caractères, l'en-tête partait en mot encodé, que Gmail ne lit pas.

        Jugé sur la forme brute, telle que `smtplib.send_message` l'écrit sur le fil : lire
        `message["List-Unsubscribe"]` redécoderait le mot encodé et ne verrait rien.
        """
        url = "https://veille.example.com/desabonnement/v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71." + "A" * 120
        texte = "Résumé : " + "une phrase accentuée, assez longue pour dépasser la ligne. " * 4
        with tempfile.TemporaryDirectory() as tmpdir:
            message = EmailSender(make_config(tmpdir))._build_message(
                "Sujet", texte, [], f"<p>{texte}</p>", desabonnement=url
            )
            # Le client réel, sans réseau : seule sa sérialisation est jugée.
            client = smtplib.SMTP()
            with mock.patch.object(client, "ehlo_or_helo_if_needed"), \
                    mock.patch.object(client, "sendmail") as sendmail:
                client.send_message(message)
            brut = sendmail.call_args.args[2]

        for serialise in (message.as_bytes(), brut):
            lignes = serialise.replace(b"\r\n", b"\n").split(b"\n")
            self.assertIn(f"List-Unsubscribe: <{url}>".encode(), lignes)
            self.assertIn(b"List-Unsubscribe-Post: List-Unsubscribe=One-Click", lignes)
            self.assertNotIn(b"=?utf-8?", serialise)
        # Le contenu, encodé sous la politique par défaut, se relit intact.
        relu = email.message_from_bytes(brut, policy=email.policy.default)
        # Aux fins de ligne du fil près (CRLF), que la relecture garde.
        self.assertEqual(texte.strip(), relu.get_body(("plain",)).get_content().strip())
        self.assertIn(texte.strip(), relu.get_body(("html",)).get_content())
        self.assertIn(b"quoted-printable", brut)
        self.assertEqual(f"<{url}>", relu["List-Unsubscribe"])
        self.assertTrue(all(len(ligne) <= 998 for ligne in brut.split(b"\r\n")))

    def test_without_a_link_there_is_no_unsubscribe_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            message = EmailSender(make_config(tmpdir))._build_message("Sujet", "Corps", [])

            self.assertIsNone(message["List-Unsubscribe"])
            self.assertIsNone(message["List-Unsubscribe-Post"])

    def test_connection_is_bounded_by_a_timeout(self):
        """Sans délai, un port sortant filtré ne se voit qu'après deux minutes muettes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(**{**make_config(tmpdir).__dict__, "smtp_use_ssl": True})
            with mock.patch.object(smtplib, "SMTP_SSL") as ssl_client:
                EmailSender(config)._connect()

            self.assertEqual(ssl_client.call_args.kwargs["timeout"], mailer.CONNECT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
