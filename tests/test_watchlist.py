"""La liste « à surveiller » : ce qui a été lu et noté sans être raconté.

Ce que ces tests protègent : les articles notés entre 4 et 6 sont déjà payés — lus,
notés, écartés. Les taire revenait à jeter la moitié de ce qu'une journée coûte. Ils
n'entrent pas dans l'audio pour autant : un titre et un lien, rien de plus.
"""

import dataclasses
import datetime as dt
import json
import tempfile
import unittest
from unittest import mock

from rssresume import runlog
from rssresume.digest import DigestService
from rssresume.models import WATCHLIST_MAX, WATCHLIST_MIN
from support import (
    FakeAudioGenerator,
    FakeEmailSender,
    FakeFreshRSSClient,
    FakeScorer,
    make_config,
)
from test_scoring_pipeline import DAY, make_article


class Harness:
    """Le pipeline complet, avec un scoring simulé et l'email retenu par une doublure."""

    def _run(self, articles, notes, config_overrides=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"], **(config_overrides or {})
            )
            email = FakeEmailSender()
            digests = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                scorer=FakeScorer(notes),
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=email,
            ).run(DAY)
            return digests, email

    @staticmethod
    def note(item_id, score):
        return {"id": item_id, "score": score, "thematique": "cyber", "angle": "a"}


class SelectionTests(Harness, unittest.TestCase):
    def test_only_the_band_between_four_and_six_is_watched(self):
        articles = [make_article(f"item-{score}") for score in range(0, 11)]
        notes = [self.note(f"item-{score}", score) for score in range(0, 11)]

        (digest,), _ = self._run(articles, notes)

        self.assertEqual(
            ["item-6", "item-5", "item-4"],
            [article.item_id for article in digest.watchlist],
        )

    def test_the_watchlist_is_ordered_by_score(self):
        articles = [make_article("bas"), make_article("haut"), make_article("milieu")]
        notes = [self.note("bas", 4), self.note("haut", 6), self.note("milieu", 5)]

        (digest,), _ = self._run(articles, notes)

        self.assertEqual(["haut", "milieu", "bas"], [a.item_id for a in digest.watchlist])

    def test_a_retained_article_is_never_also_watched(self):
        """Le seuil de repli descend à 5 : les 5 et 6 sont retenus, donc plus surveillés."""
        articles = [make_article(f"item-{score}") for score in (4, 5, 6)]
        notes = [self.note(f"item-{score}", score) for score in (4, 5, 6)]

        (digest,), _ = self._run(
            articles, notes, {"fallback_threshold": 5, "min_digest_items": 3}
        )

        self.assertEqual(["item-6", "item-5"], [a.item_id for a in digest.selected])
        self.assertEqual(["item-4"], [a.item_id for a in digest.watchlist])

    def test_a_category_with_nothing_retained_still_offers_its_watchlist(self):
        """C'est le cas où elle sert le plus : rien à raconter, mais des liens à donner."""
        articles = [make_article("item-a"), make_article("item-b")]
        notes = [self.note("item-a", 6), self.note("item-b", 1)]

        (digest,), email = self._run(articles, notes)

        self.assertEqual([], digest.selected)
        self.assertEqual(["item-a"], [a.item_id for a in digest.watchlist])
        self.assertIn("À surveiller :", email.messages[0][1])

    def test_an_article_without_a_url_never_becomes_a_link(self):
        articles = [
            dataclasses.replace(make_article("sans-url"), url=""),
            make_article("avec-url"),
        ]
        notes = [self.note("sans-url", 5), self.note("avec-url", 5)]

        (digest,), _ = self._run(articles, notes)

        self.assertEqual(2, len(digest.watchlist))
        self.assertEqual(["Titre avec-url"], [lien.title for lien in digest.watchlist_links])


class SansScoringTests(Harness, unittest.TestCase):
    def test_without_a_scorer_nothing_is_watched(self):
        """Sans noteur, tout entre dans le digest : il n'y a pas de bande intermédiaire."""
        with tempfile.TemporaryDirectory() as tmpdir:
            digests = DigestService(
                config=dataclasses.replace(make_config(tmpdir), categories=["Tech"]),
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article("item-1")]}),
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)

            self.assertEqual([], digests[0].watchlist)


class RelectureTests(unittest.TestCase):
    """La liste se recalcule des scores du journal, sans avoir été stockée à côté."""

    def _journal(self, tmpdir, articles):
        day_dir = tmpdir / DAY.isoformat()
        day_dir.mkdir(parents=True)
        (day_dir / "tech.log.json").write_text(
            json.dumps(
                {"categorie": "Tech", "date": DAY.isoformat(), "resume": "r", "articles": articles},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return day_dir

    @staticmethod
    def entree(item_id, score, retenu=False):
        return {
            "item_id": item_id,
            "titre": item_id,
            "flux": "Flux",
            "url": f"https://x.test/{item_id}",
            "score": score,
            "retenu": retenu,
        }

    def test_a_past_day_is_reread_with_its_watchlist(self):
        import pathlib

        with tempfile.TemporaryDirectory() as tmpdir:
            day_dir = self._journal(
                pathlib.Path(tmpdir),
                [
                    self.entree("retenu", 9, retenu=True),
                    self.entree("surveille", 5),
                    self.entree("trop-bas", 2),
                    self.entree("sans-note", None),
                ],
            )

            digest, = runlog.read_day(day_dir)

            self.assertEqual(["retenu"], [lien.title for lien in digest.links])
            self.assertEqual(["surveille"], [lien.title for lien in digest.watchlist_links])


class FourchetteTests(unittest.TestCase):
    def test_the_band_is_a_display_rule_stated_once(self):
        """Une seule paire de bornes, pour la production comme pour la relecture."""
        self.assertEqual(4, WATCHLIST_MIN)
        self.assertEqual(6, WATCHLIST_MAX)
        self.assertLess(WATCHLIST_MIN, WATCHLIST_MAX)


if __name__ == "__main__":
    unittest.main()
