import datetime as dt
import tempfile
import unittest

from rssresume.models import Article
from rssresume.summaries import SummaryGenerator
from support import make_config


class SummaryGeneratorTests(unittest.TestCase):
    def test_fallback_summary_is_audio_friendly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            article = Article(
                item_id="item-1",
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

    def test_summary_without_article_needs_no_backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = SummaryGenerator(make_config(tmpdir)).summarize("Tech", [])

            self.assertEqual("Aucun nouvel article aujourd'hui dans la catégorie Tech.", summary)


if __name__ == "__main__":
    unittest.main()
