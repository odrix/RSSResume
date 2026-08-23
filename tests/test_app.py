import datetime as dt
import pathlib
import tempfile
import unittest

from rssresume.app import AppConfig, Article, DigestService, EmailSender, SummaryGenerator


class FakeFreshRSSClient:
    def __init__(self, articles_by_category):
        self._articles_by_category = articles_by_category

    def list_categories(self):
        return list(self._articles_by_category)

    def fetch_daily_articles(self, category, day):
        return self._articles_by_category[category]


class FakeAudioGenerator:
    def synthesize(self, text, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return output_path


class FakeEmailSender:
    def __init__(self):
        self.messages = []

    def is_configured(self):
        return True

    def send(self, subject, body, attachments):
        self.messages.append((subject, body, list(attachments)))


def make_config(output_dir):
    return AppConfig(
        freshrss_base_url="https://example.com",
        freshrss_username="user",
        freshrss_api_password="password",
        output_dir=pathlib.Path(output_dir),
        categories=["Tech", "News"],
        summary_language="fr",
        summary_model=None,
        tts_model=None,
        tts_voice=None,
        llm_base_url=None,
        llm_api_key=None,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-pass",
        smtp_from="from@example.com",
        smtp_to=["to@example.com"],
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )


class DigestServiceTests(unittest.TestCase):
    def test_run_generates_one_audio_per_category_and_sends_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            today = dt.date(2026, 8, 23)
            article = Article(
                category="Tech",
                title="Nouveau modèle",
                url="https://example.com/article",
                published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
                feed_title="AI Feed",
                content_text="Un nouveau modèle améliore les performances.",
            )
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [article], "News": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(today)

            self.assertEqual(["Tech", "News"], [digest.category for digest in digests])
            self.assertEqual(1, len(email_sender.messages))
            attachments = email_sender.messages[0][2]
            self.assertEqual(2, len(attachments))
            self.assertTrue(all(path.exists() for path in attachments))
            self.assertIn("Nouveau modèle", attachments[0].read_text(encoding="utf-8"))
            self.assertIn("Aucun nouvel article", attachments[1].read_text(encoding="utf-8"))

    def test_run_uses_discovered_categories_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "categories": []})
            today = dt.date(2026, 8, 23)
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Culture": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(today, send_email=False)

            self.assertEqual(["Culture"], [digest.category for digest in digests])
            self.assertEqual([], email_sender.messages)


class SummaryGeneratorTests(unittest.TestCase):
    def test_fallback_summary_is_audio_friendly(self):
        config = make_config("/tmp")
        article = Article(
            category="Tech",
            title="Titre",
            url="https://example.com/article",
            published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
            feed_title="Feed",
            content_text="Contenu test pour le résumé.",
        )

        summary = SummaryGenerator(config).summarize("Tech", [article])

        self.assertIn("Résumé quotidien pour la catégorie Tech", summary)
        self.assertIn("Fin du résumé du jour.", summary)


class EmailSenderTests(unittest.TestCase):
    def test_email_sender_detects_incomplete_configuration(self):
        config = make_config("/tmp")
        config = AppConfig(**{**config.__dict__, "smtp_host": None})

        self.assertFalse(EmailSender(config).is_configured())


if __name__ == "__main__":
    unittest.main()

