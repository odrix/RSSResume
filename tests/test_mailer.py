import email.utils
import smtplib
import tempfile
import unittest
from unittest import mock

from rssresume.config import AppConfig
from rssresume.external import mailer
from rssresume.external.mailer import EmailSender
from support import make_config


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

    def test_connection_is_bounded_by_a_timeout(self):
        """Sans délai, un port sortant filtré ne se voit qu'après deux minutes muettes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig(**{**make_config(tmpdir).__dict__, "smtp_use_ssl": True})
            with mock.patch.object(smtplib, "SMTP_SSL") as ssl_client:
                EmailSender(config)._connect()

            self.assertEqual(ssl_client.call_args.kwargs["timeout"], mailer.CONNECT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
