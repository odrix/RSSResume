"""Intégration du scoring dans le pipeline : cache par empreinte de prompt et sélection."""

import dataclasses
import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume.digest import DigestService
from rssresume.freshrss import score_tag, scoring_tag
from rssresume.models import Article
from rssresume.processing import scoring_prompt_digest
from support import FakeAudioGenerator, FakeEmailSender, FakeFreshRSSClient, make_config

DAY = dt.date(2026, 8, 23)


def make_article(item_id, tags=()):
    return Article(
        item_id=item_id,
        category="Tech",
        title=f"Titre {item_id}",
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text="Contenu de l'article.",
        tags=tags,
    )


class PipelineHarness:
    """Monte le pipeline avec une API configurée et un scoring simulé."""

    def _run(self, articles, notes, config_overrides=None, **kwargs):
        """Exécute le pipeline avec une API configurée et un scoring simulé."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir),
                categories=["Tech"],
                llm_base_url="https://api.example/v1",
                llm_api_key="key",
                summary_model="gpt-4o-mini",
                **(config_overrides or {}),
            )
            client = FakeFreshRSSClient({"Tech": articles})
            with mock.patch("rssresume.digest.processing.score_articles", return_value=notes) as scorer:
                service = DigestService(
                    config=config,
                    freshrss_client=client,
                    summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                    audio_generator=FakeAudioGenerator(),
                    email_sender=FakeEmailSender(),
                )
                digests = service.run(DAY, send_email=False, **kwargs)
            return client, scorer, digests

    @staticmethod
    def note(item_id, score):
        return {"id": item_id, "score": score, "thematique": "cyber", "angle": "a"}


class ScoringPipelineTests(PipelineHarness, unittest.TestCase):
    def test_only_selected_articles_are_tagged_digested(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 3)]

        client, _, _ = self._run(articles, notes)

        self.assertEqual(["item-1"], client.digested)
        # Tous les articles restent marqués comme lus, pas seulement les retenus.
        self.assertEqual(["item-1", "item-2"], [a.item_id for a in client.marked_as_read])

    def test_scores_are_written_with_the_prompt_digest(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 3)]

        client, _, _ = self._run(articles, notes)

        self.assertEqual({"item-1": 9, "item-2": 3}, client.scored)
        self.assertEqual(scoring_prompt_digest(), client.scoring_digest)

    def test_already_scored_articles_are_not_rescored(self):
        courant = scoring_prompt_digest()
        articles = [
            make_article("item-1", tags=(scoring_tag(courant), score_tag(9))),
            make_article("item-2", tags=(scoring_tag(courant), score_tag(2))),
        ]

        client, scorer, _ = self._run(articles, [])

        scorer.assert_not_called()
        self.assertEqual({}, client.scored)
        # Le score relu des tags pilote quand même la sélection.
        self.assertEqual(["item-1"], client.digested)

    def test_stale_prompt_digest_triggers_rescoring_and_cleanup(self):
        articles = [
            make_article("item-1", tags=(scoring_tag("0123456789ab"), score_tag(2))),
            make_article("item-2", tags=(scoring_tag(scoring_prompt_digest()), score_tag(8))),
        ]

        client, scorer, _ = self._run(articles, [self.note("item-1", 9)])

        scorer.assert_called_once()
        self.assertEqual(["item-1"], [a["id"] for a in scorer.call_args.args[0]])
        self.assertEqual(["item-1"], client.cleared)
        self.assertEqual({"item-1": 9}, client.scored)

    def test_scoring_payload_carries_an_excerpt_not_the_full_text(self):
        article = make_article("item-1")
        article = dataclasses.replace(article, content_text="x" * 5000)

        _, scorer, _ = self._run([article], [self.note("item-1", 9)])

        payload = scorer.call_args.args[0][0]
        self.assertEqual(400, len(payload["summary"]))
        self.assertNotIn("content", payload)

    def test_selection_is_sorted_by_score_and_capped(self):
        articles = [make_article(f"item-{i}") for i in range(5)]
        # Scores 7, 8, 9, 10, 7 : l'ordre attendu est item-3, item-2, item-1.
        notes = [self.note(f"item-{i}", score) for i, score in enumerate([7, 8, 9, 10, 7])]

        _, _, digests = self._run(articles, notes, config_overrides={"max_digest_items": 3})

        self.assertEqual(["item-3", "item-2", "item-1"], [a.item_id for a in digests[0].selected])

    def test_threshold_is_read_from_the_config(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 5)]

        _, _, digests = self._run(articles, notes, config_overrides={"score_threshold": 5})

        self.assertEqual(["item-1", "item-2"], sorted(a.item_id for a in digests[0].selected))

    def test_summary_receives_only_the_selection(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 1)]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"],
                llm_base_url="https://api.example/v1", llm_api_key="key", summary_model="m",
            )
            generator = mock.Mock(summarize=mock.Mock(return_value="résumé"))
            with mock.patch("rssresume.digest.processing.score_articles", return_value=notes):
                DigestService(
                    config=config,
                    freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                    summary_generator=generator,
                    audio_generator=FakeAudioGenerator(),
                    email_sender=FakeEmailSender(),
                ).run(DAY, send_email=False)

        recus = generator.summarize.call_args.args[1]
        self.assertEqual(["item-1"], [a.item_id for a in recus])

    def test_below_threshold_yields_an_empty_selection(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 3), self.note("item-2", 1)]

        client, _, digests = self._run(articles, notes)

        self.assertEqual([], digests[0].selected)
        self.assertEqual([], client.digested)

    def test_dry_run_writes_nothing_to_freshrss(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(
            articles, [self.note("item-1", 9)], write_tags=False, mark_read=False
        )

        self.assertEqual([], client.digested)
        self.assertEqual({}, client.scored)
        self.assertEqual([], client.cleared)
        self.assertEqual([], client.marked_as_read)


class WriteFlagsTests(PipelineHarness, unittest.TestCase):
    """Les deux axes d'écriture FreshRSS sont indépendants."""

    def test_no_mark_read_still_writes_the_score_cache(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)], mark_read=False)

        # C'est l'intérêt du découpage : le scoring n'est pas repayé au prochain essai.
        self.assertEqual({"item-1": 9}, client.scored)
        self.assertEqual(scoring_prompt_digest(), client.scoring_digest)
        self.assertEqual(["item-1"], client.digested)
        self.assertEqual([], client.marked_as_read)

    def test_no_tags_still_marks_articles_as_read(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)], write_tags=False)

        self.assertEqual({}, client.scored)
        self.assertEqual([], client.digested)
        self.assertEqual([], client.cleared)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])

    def test_tags_survive_an_email_failure(self):
        """Les tags sont ecrits par categorie, avant l'envoi : un echec les preserve."""
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 2)]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"],
                llm_base_url="https://api.example/v1", llm_api_key="key", summary_model="m",
            )
            client = FakeFreshRSSClient({"Tech": articles})
            sender = FakeEmailSender()
            sender.send = mock.Mock(side_effect=RuntimeError("SMTP down"))
            with mock.patch("rssresume.digest.processing.score_articles", return_value=notes):
                service = DigestService(
                    config=config,
                    freshrss_client=client,
                    summary_generator=mock.Mock(summarize=mock.Mock(return_value="r")),
                    audio_generator=FakeAudioGenerator(),
                    email_sender=sender,
                )
                with self.assertRaises(RuntimeError):
                    service.run(DAY)

        # Scores et tag digest conserves : le prochain passage ne repaie pas le scoring.
        self.assertEqual({"item-1": 9, "item-2": 2}, client.scored)
        self.assertEqual(["item-1"], client.digested)
        # Le marquage comme lu, lui, n'a pas eu lieu : les articles seront repris.
        self.assertEqual([], client.marked_as_read)

    def test_tags_of_earlier_categories_survive_a_later_failure(self):
        """Une categorie qui casse ne fait pas perdre les scores des precedentes."""
        tech = [make_article("item-1")]
        news = [make_article("item-2")]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech", "News"],
                llm_base_url="https://api.example/v1", llm_api_key="key", summary_model="m",
            )
            client = FakeFreshRSSClient({"Tech": tech, "News": news})
            appels = [[self.note("item-1", 9)], RuntimeError("API down")]

            def scorer(payload, credentials=None):
                resultat = appels.pop(0)
                if isinstance(resultat, Exception):
                    raise resultat
                return resultat

            with mock.patch("rssresume.digest.processing.score_articles", side_effect=scorer):
                with self.assertRaises(RuntimeError):
                    DigestService(
                        config=config,
                        freshrss_client=client,
                        summary_generator=mock.Mock(summarize=mock.Mock(return_value="r")),
                        audio_generator=FakeAudioGenerator(),
                        email_sender=FakeEmailSender(),
                    ).run(DAY, send_email=False)

        self.assertEqual({"item-1": 9}, client.scored)
        self.assertEqual(["item-1"], client.digested)

    def test_default_run_writes_everything(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)])

        self.assertEqual({"item-1": 9}, client.scored)
        self.assertEqual(["item-1"], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])


if __name__ == "__main__":
    unittest.main()
