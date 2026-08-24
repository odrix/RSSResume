import datetime as dt
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.models import Article
from rssresume.summaries import SummaryGenerator
from support import FakeAudioGenerator, FakeEmailSender, FakeFreshRSSClient, make_config

DAY = dt.date(2026, 8, 23)


def make_article(category="Tech", title="Nouveau modèle", item_id="item-1"):
    return Article(
        item_id=item_id,
        category=category,
        title=title,
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="AI Feed",
        content_text="Un nouveau modèle améliore les performances.",
    )


class MarkAsReadTests(unittest.TestCase):
    def _run(self, articles_by_category, **kwargs):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            client = FakeFreshRSSClient(articles_by_category)
            service = DigestService(
                config=config,
                freshrss_client=client,
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )
            service.run(DAY, **kwargs)
            return client

    def test_processed_articles_are_marked_as_read(self):
        articles = [make_article(item_id="item-1"), make_article(item_id="item-2")]
        client = self._run({"Tech": articles, "News": []}, send_email=False)

        self.assertEqual(["item-1", "item-2"], [article.item_id for article in client.marked_as_read])

    def test_dry_run_does_not_mark_articles_as_read(self):
        client = self._run({"Tech": [make_article()], "News": []}, send_email=False, write_tags=False, mark_read=False)

        self.assertEqual([], client.marked_as_read)

    def test_empty_categories_trigger_no_marking(self):
        client = self._run({"Tech": [], "News": []}, send_email=False)

        self.assertEqual([], client.marked_as_read)

    def test_digested_articles_are_tagged(self):
        articles = [make_article(item_id="item-1"), make_article(item_id="item-2")]
        client = self._run({"Tech": articles, "News": []}, send_email=False)

        self.assertEqual(["item-1", "item-2"], client.digested)

    def test_dry_run_does_not_tag_digested_articles(self):
        client = self._run({"Tech": [make_article()], "News": []}, send_email=False, write_tags=False, mark_read=False)

        self.assertEqual([], client.digested)

    def test_empty_categories_are_not_tagged(self):
        client = self._run({"Tech": [], "News": []}, send_email=False)

        self.assertEqual([], client.digested)


class DigestServiceTests(unittest.TestCase):
    def test_run_generates_one_audio_per_non_empty_category_and_sends_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article()], "News": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(DAY)

            self.assertEqual(["Tech", "News"], [digest.category for digest in digests])
            self.assertIn("Nouveau modèle", digests[0].summary_text)
            self.assertIn("Aucun nouvel article", digests[1].summary_text)
            self.assertEqual(1, len(email_sender.messages))
            self.assertEqual([pathlib.Path(tmpdir) / "2026-08-23" / "tech.wav"], email_sender.messages[0][2])

    def test_run_writes_one_directory_per_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article()], "News": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            day_dir = pathlib.Path(tmpdir) / "2026-08-23"
            self.assertEqual(day_dir, digests[0].audio_path.parent)
            self.assertEqual(day_dir, digests[1].marker_path.parent)

    def test_run_writes_empty_marker_instead_of_audio_for_empty_category(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [], "News": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            marker = digests[0].marker_path
            self.assertIsNone(digests[0].audio_path)
            self.assertEqual(pathlib.Path(tmpdir) / "2026-08-23" / "tech.no-article", marker)
            self.assertTrue(marker.exists())
            self.assertEqual(0, marker.stat().st_size)

    def test_run_never_calls_generators_for_empty_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_generator = mock.Mock()
            audio_generator = mock.Mock()
            service = DigestService(
                config=make_config(tmpdir),
                freshrss_client=FakeFreshRSSClient({"Tech": [], "News": []}),
                summary_generator=summary_generator,
                audio_generator=audio_generator,
                email_sender=FakeEmailSender(),
            )

            service.run(DAY, send_email=False)

            summary_generator.summarize.assert_not_called()
            audio_generator.synthesize.assert_not_called()

    def test_run_uses_discovered_categories_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "categories": []})
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Culture": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(DAY, send_email=False)

            self.assertEqual(["Culture"], [digest.category for digest in digests])
            self.assertEqual([], email_sender.messages)

    def test_run_skips_excluded_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "categories": [], "excluded_categories": ["non classé"]})
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [], "Non classé": []}),
                summary_generator=SummaryGenerator(config),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            self.assertEqual(["Tech"], [digest.category for digest in digests])


if __name__ == "__main__":
    unittest.main()
