import dataclasses
import datetime as dt
import tempfile
import unittest
import zoneinfo
from unittest import mock

from rssresume.config import AppConfig

from rssresume.external.freshrss import (
    DIGEST_TAG,
    EDIT_TAG_BATCH_SIZE,
    LABEL_STREAM_PREFIX,
    READ_STATE,
    FreshRSSClient,
)
from rssresume.models import Article, Note
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


def fetch(pages, day=dt.date(2026, 8, 23), include_read=False, timezone="Europe/Paris"):
    """Récupère une journée sur des pages simulées ; rend (articles, appels passés).

    `pages` est une réponse unique ou la liste des réponses successives de l'API.
    Chaque appel est relevé sous la forme (chemin, paramètres). Le fuseau est celui qui
    découpe la journée : c'est lui qui décide où tombe un article de la nuit.
    """
    reponses = [pages] if isinstance(pages, dict) else list(pages)
    appels = []

    def _json_get(self, path, params=None):
        appels.append((path, params or {}))
        return reponses[len(appels) - 1]

    with tempfile.TemporaryDirectory() as tmpdir:
        config = make_config(tmpdir)
        config = AppConfig(**{**config.__dict__, "timezone": zoneinfo.ZoneInfo(timezone)})
        client = FreshRSSClient(config, include_read=include_read)
        with mock.patch.object(FreshRSSClient, "_json_get", _json_get):
            return client.fetch_daily_articles("Tech", day), appels


def paris(year, month, day, hour, minute=0):
    """Un horodatage donné à l'heure de Paris, tel que FreshRSS le publierait."""
    return dt.datetime(
        year, month, day, hour, minute, tzinfo=zoneinfo.ZoneInfo("Europe/Paris")
    ).timestamp()


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
        """Le filtre Python reste en filet : il tient la borne haute, et couvre un `ot` ignoré."""
        day = dt.date(2026, 8, 23)
        payload = {
            "items": [
                {
                    "title": "Gardé",
                    "published": paris(2026, 8, 23, 10),
                    "summary": {"content": "<p>Texte</p>"},
                },
                {"title": "Trop tôt", "published": paris(2026, 8, 22, 23)},
                {"title": "Trop tard", "published": paris(2026, 8, 24, 3)},
            ]
        }

        articles, _ = fetch(payload, day=day)

        self.assertEqual(["Gardé"], [article.title for article in articles])
        self.assertEqual("Texte", articles[0].content_text)

    def test_a_night_article_belongs_to_the_local_day_not_the_utc_one(self):
        """00h30 à Paris en été, c'est 22h30 la veille en UTC : l'article disparaissait.

        La veille étant déjà livrée et ses articles marqués lus, il n'apparaissait
        ensuite dans aucun digest — un décalage muet, invisible sans le chercher.
        """
        payload = {"items": [{"title": "Publié à 00h30", "published": paris(2026, 8, 23, 0, 30)}]}

        articles, _ = fetch(payload, day=dt.date(2026, 8, 23))

        self.assertEqual(["Publié à 00h30"], [article.title for article in articles])

    def test_the_timezone_is_configurable(self):
        """Le même horodatage, lu en UTC, tombe dans la journée précédente."""
        payload = {"items": [{"title": "Publié à 00h30", "published": paris(2026, 8, 23, 0, 30)}]}

        articles, _ = fetch(payload, day=dt.date(2026, 8, 23), timezone="UTC")

        self.assertEqual([], articles)

    def test_fetch_daily_articles_filters_on_the_api_side(self):
        """Paginer tout le flux pour en garder vingt coûtait des dizaines d'appels par jour."""
        day = dt.date(2026, 8, 23)

        _, appels = fetch({"items": []}, day=day)

        (_, params), = appels
        # Borne basse de la journée, en secondes : minuit à Paris, soit 22h UTC la veille.
        self.assertEqual(str(int(paris(2026, 8, 23, 0))), params["ot"])
        # Un article lu est un article déjà digéré : il n'a rien à faire dans le lot.
        self.assertEqual(READ_STATE, params["xt"])

    def test_fetch_daily_articles_repeats_the_filters_on_every_page(self):
        """La continuation dit où reprendre, pas ce qu'on demandait : sans les filtres, la
        deuxième page ramenait de nouveau tout le flux."""
        pages = [
            {"items": [{"title": "Un", "published": 0}], "continuation": "page-2"},
            {"items": [{"title": "Deux", "published": 0}]},
        ]

        _, appels = fetch(pages)

        self.assertEqual(2, len(appels))
        premiers, seconds = (params for _, params in appels)
        self.assertNotIn("c", premiers)
        self.assertEqual("page-2", seconds["c"])
        self.assertEqual(premiers["ot"], seconds["ot"])
        self.assertEqual(premiers["xt"], seconds["xt"])

    def test_include_read_asks_for_the_articles_already_read(self):
        """Rejouer une journée close : ses articles sont lus, il faut les redemander."""
        _, appels = fetch({"items": []}, include_read=True)

        (_, params), = appels
        self.assertNotIn("xt", params)
        self.assertIn("ot", params)


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
        notes = {
            "item-1": Note(9, "cyber", "a"),
            "item-2": Note(3, "cyber", "a"),
            "item-3": Note(9, "cyber", "a"),
        }

        post_form = capture_posts(lambda client: client.tag_notes(notes))

        # Deux valeurs de score, une seule thématique : trois appels.
        self.assertEqual(3, post_form.call_count)
        labels = [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]
        self.assertEqual(
            [
                ("a", f"{LABEL_STREAM_PREFIX}score-03"),
                ("a", f"{LABEL_STREAM_PREFIX}score-09"),
                ("a", f"{LABEL_STREAM_PREFIX}theme-cyber"),
            ],
            labels,
        )
        neuf = post_form.call_args_list[1].args[1][2:]
        self.assertEqual([("i", "item-1"), ("i", "item-3")], neuf)

    def test_thematique_is_tagged_so_the_cache_can_group_later(self):
        """Sans ce tag, un score relu du cache ne saurait plus dans quel groupe ranger l'article."""
        notes = {"item-1": Note(9, "reglementaire", "a"), "item-2": Note(9, "cyber", "a")}

        post_form = capture_posts(lambda client: client.tag_notes(notes))

        labels = [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]
        self.assertEqual(
            [
                ("a", f"{LABEL_STREAM_PREFIX}score-09"),
                ("a", f"{LABEL_STREAM_PREFIX}theme-cyber"),
                ("a", f"{LABEL_STREAM_PREFIX}theme-reglementaire"),
            ],
            labels,
        )
        self.assertEqual([("i", "item-2")], post_form.call_args_list[1].args[1][2:])

    def test_score_tag_is_zero_padded_for_alphabetical_order(self):
        post_form = capture_posts(lambda client: client.tag_notes({"item-1": Note(7)}))

        self.assertEqual(f"{LABEL_STREAM_PREFIX}score-07", post_form.call_args_list[0].args[1][1][1])

    def test_clearing_scoring_tags_removes_only_the_tags_actually_carried(self):
        articles = [
            make_article("item-1"),
            make_article("item-2"),
        ]
        articles[0] = dataclasses.replace(
            articles[0], tags=("score-02", "scoring-abc123", "theme-cyber", "digested")
        )
        articles[1] = dataclasses.replace(articles[1], tags=("score-09", "scoring-abc123"))

        post_form = capture_posts(lambda client: client.clear_scoring_tags(articles))

        # Quatre tags distincts portés : les deux scores, l'empreinte et la thématique.
        # 'digested' est préservé : il dit que l'article est passé dans un digest, pas comment.
        self.assertEqual(4, post_form.call_count)
        appels = [fields[1] for _, fields in (call.args for call in post_form.call_args_list)]
        self.assertEqual(
            [
                ("r", f"{LABEL_STREAM_PREFIX}score-02"),
                ("r", f"{LABEL_STREAM_PREFIX}score-09"),
                ("r", f"{LABEL_STREAM_PREFIX}scoring-abc123"),
                ("r", f"{LABEL_STREAM_PREFIX}theme-cyber"),
            ],
            appels,
        )
        self.assertEqual([("i", "item-1")], post_form.call_args_list[-1].args[1][2:])

    def test_score_tags_carry_the_prompt_digest(self):
        post_form = capture_posts(
            lambda client: client.tag_notes({"item-1": Note(9, "cyber", "a")}, "abc123")
        )

        self.assertEqual(3, post_form.call_count)
        self.assertEqual(f"{LABEL_STREAM_PREFIX}score-09", post_form.call_args_list[0].args[1][1][1])
        self.assertEqual(f"{LABEL_STREAM_PREFIX}theme-cyber", post_form.call_args_list[1].args[1][1][1])
        self.assertEqual(f"{LABEL_STREAM_PREFIX}scoring-abc123", post_form.call_args_list[2].args[1][1][1])

    def test_tagging_without_item_makes_no_request(self):
        self.assertEqual(0, capture_posts(lambda client: client.mark_digested([])).call_count)
        self.assertEqual(0, capture_posts(lambda client: client.tag_notes({})).call_count)


if __name__ == "__main__":
    unittest.main()
