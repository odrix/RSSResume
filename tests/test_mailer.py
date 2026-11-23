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
