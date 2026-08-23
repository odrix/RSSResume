import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume.freshrss import EDIT_TAG_BATCH_SIZE, READ_STATE, FreshRSSClient
from rssresume.models import Article
from support import make_config


def make_article(item_id):
    return Article(
        item_id=item_id,
        category="Tech",
        title="Titre",
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text="Contenu.",
    )


class FreshRSSClientTests(unittest.TestCase):
    def test_list_categories_ignores_feeds_without_user_label(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FreshRSSClient(make_config(tmpdir))
            payload = {
                "subscriptions": [
                    {"id": "feed/1", "categories": [{"id": "user/-/label/Tech", "label": "Tech"}]},
                    {"id": "feed/2", "categories": []},
                    {"id": "feed/3", "categories": [{"id": "user/-/state/com.google/reading-list", "label": "Tous"}]},
                ]
            }
            with mock.patch.object(FreshRSSClient, "_json_get", return_value=payload):
                self.assertEqual(["Tech"], client.list_categories())

    def test_fetch_daily_articles_keeps_only_the_requested_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FreshRSSClient(make_config(tmpdir))
            day = dt.date(2026, 8, 23)
            in_day = dt.datetime(2026, 8, 23, 10, 0, tzinfo=dt.timezone.utc).timestamp()
            day_before = dt.datetime(2026, 8, 22, 23, 0, tzinfo=dt.timezone.utc).timestamp()
            payload = {
                "items": [
                    {"title": "Gardé", "published": in_day, "summary": {"content": "<p>Texte</p>"}},
                    {"title": "Trop tôt", "published": day_before},
                ]
            }
            with mock.patch.object(FreshRSSClient, "_json_get", return_value=payload):
                articles = client.fetch_daily_articles("Tech", day)

            self.assertEqual(["Gardé"], [article.title for article in articles])
            self.assertEqual("Texte", articles[0].content_text)


class MarkAsReadTests(unittest.TestCase):
    def _mark(self, articles):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FreshRSSClient(make_config(tmpdir))
            with mock.patch.object(FreshRSSClient, "_ensure_edit_token", return_value="csrf-token"):
                with mock.patch.object(FreshRSSClient, "_post_form") as post_form:
                    client.mark_as_read(articles)
            return post_form

    def test_mark_as_read_posts_edit_tag_with_read_state(self):
        post_form = self._mark([make_article("item-1"), make_article("item-2")])

        post_form.assert_called_once()
        path, fields = post_form.call_args.args
        self.assertEqual("/api/greader.php/reader/api/0/edit-tag", path)
        self.assertEqual([("T", "csrf-token"), ("a", READ_STATE), ("i", "item-1"), ("i", "item-2")], fields)

    def test_mark_as_read_batches_large_selections(self):
        articles = [make_article(f"item-{index}") for index in range(EDIT_TAG_BATCH_SIZE + 1)]

        post_form = self._mark(articles)

        self.assertEqual(2, post_form.call_count)
        last_fields = post_form.call_args_list[-1].args[1]
        self.assertEqual([("i", f"item-{EDIT_TAG_BATCH_SIZE}")], last_fields[2:])

    def test_mark_as_read_without_article_makes_no_request(self):
        self.assertEqual(0, self._mark([]).call_count)


if __name__ == "__main__":
    unittest.main()
