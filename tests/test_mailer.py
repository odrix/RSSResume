import tempfile
import unittest

from rssresume.config import AppConfig
from rssresume.mailer import EmailSender
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


if __name__ == "__main__":
    unittest.main()
