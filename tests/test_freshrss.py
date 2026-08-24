import dataclasses
import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume.freshrss import (
    DIGEST_TAG,
    EDIT_TAG_BATCH_SIZE,
    LABEL_STREAM_PREFIX,
    READ_STATE,
    FreshRSSClient,
)
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


def capture_posts(action):
    """Exécute `action(client)` en interceptant les appels edit-tag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = FreshRSSClient(make_config(tmpdir))
        with mock.patch.object(FreshRSSClient, "_ensure_edit_token", return_value="csrf-token"):
            with mock.patch.object(FreshRSSClient, "_post_form") as post_form:
                action(client)
        return post_form


class MarkAsReadTests(unittest.TestCase):
    def _mark(self, articles):
        return capture_posts(lambda client: client.mark_as_read(articles))

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


class TagTests(unittest.TestCase):
    def test_digest_tag_uses_a_user_label(self):
        post_form = capture_posts(lambda client: client.mark_digested(["item-1", "item-2"]))

        post_form.assert_called_once()
        path, fields = post_form.call_args.args
        self.assertEqual("/api/greader.php/reader/api/0/edit-tag", path)
        self.assertEqual(
            [
                ("T", "csrf-token"),
                ("a", f"{LABEL_STREAM_PREFIX}{DIGEST_TAG}"),
                ("i", "item-1"),
                ("i", "item-2"),
            ],
            fields,
        )

    def test_digest_tag_batches_large_selections(self):
        item_ids = [f"item-{index}" for index in range(EDIT_TAG_BATCH_SIZE + 1)]

        post_form = capture_posts(lambda client: client.mark_digested(item_ids))

        self.assertEqual(2, post_form.call_count)
        self.assertEqual([("i", f"item-{EDIT_TAG_BATCH_SIZE}")], post_form.call_args_list[-1].args[1][2:])

    def test_scores_are_grouped_one_call_per_distinct_value(self):
        scores = {"item-1": 9, "item-2": 3, "item-3": 9}

        post_form = capture_posts(lambda client: client.tag_scores(scores))

        self.assertEqual(2, post_form.call_count)
        labels = [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]
        self.assertEqual(
            [("a", f"{LABEL_STREAM_PREFIX}score-03"), ("a", f"{LABEL_STREAM_PREFIX}score-09")],
            labels,
        )
        neuf = post_form.call_args_list[-1].args[1][2:]
        self.assertEqual([("i", "item-1"), ("i", "item-3")], neuf)

    def test_score_tag_is_zero_padded_for_alphabetical_order(self):
        post_form = capture_posts(lambda client: client.tag_scores({"item-1": 7}))

        self.assertEqual(f"{LABEL_STREAM_PREFIX}score-07", post_form.call_args.args[1][1][1])

    def test_clearing_scoring_tags_removes_only_the_tags_actually_carried(self):
        articles = [
            make_article("item-1"),
            make_article("item-2"),
        ]
        articles[0] = dataclasses.replace(articles[0], tags=("score-02", "scoring-abc123", "digested"))
        articles[1] = dataclasses.replace(articles[1], tags=("score-09", "scoring-abc123"))

        post_form = capture_posts(lambda client: client.clear_scoring_tags(articles))

        # Trois tags distincts portés : score-02, score-09, scoring-abc123. 'digested' est préservé.
        self.assertEqual(3, post_form.call_count)
        appels = [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]
        self.assertEqual(
            [
                ("r", f"{LABEL_STREAM_PREFIX}score-02"),
                ("r", f"{LABEL_STREAM_PREFIX}score-09"),
                ("r", f"{LABEL_STREAM_PREFIX}scoring-abc123"),
            ],
            appels,
        )
        self.assertEqual([("i", "item-1"), ("i", "item-2")], post_form.call_args_list[-1].args[1][2:])

    def test_score_tags_carry_the_prompt_digest(self):
        post_form = capture_posts(lambda client: client.tag_scores({"item-1": 9}, "abc123"))

        self.assertEqual(2, post_form.call_count)
        self.assertEqual(f"{LABEL_STREAM_PREFIX}score-09", post_form.call_args_list[0].args[1][1][1])
        self.assertEqual(f"{LABEL_STREAM_PREFIX}scoring-abc123", post_form.call_args_list[1].args[1][1][1])

    def test_tagging_without_item_makes_no_request(self):
        self.assertEqual(0, capture_posts(lambda client: client.mark_digested([])).call_count)
        self.assertEqual(0, capture_posts(lambda client: client.tag_scores({})).call_count)


if __name__ == "__main__":
    unittest.main()
