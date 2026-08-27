"""Intégration du scoring dans le pipeline : cache par empreinte de prompt et sélection."""

import dataclasses
import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume.digest import DigestService
from rssresume.external.freshrss import score_tag, scoring_tag, theme_tag
from rssresume.models import Article, Note
from support import FakeAudioGenerator, FakeEmailSender, FakeFreshRSSClient, FakeScorer, empreinte, make_config

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
                **(config_overrides or {}),
            )
            client = FakeFreshRSSClient({"Tech": articles})
            scorer = FakeScorer(notes)
            digests = DigestService(
                config=config,
                freshrss_client=client,
                scorer=scorer,
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False, **kwargs)
            return client, scorer.score_articles, digests

    @staticmethod
    def note(item_id, score, thematique="cyber", angle="a"):
        return {"id": item_id, "score": score, "thematique": thematique, "angle": angle}


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
        self.assertEqual(empreinte(), client.scoring_digest)

    def test_already_scored_articles_are_not_rescored(self):
        courant = empreinte()
        articles = [
            make_article("item-1", tags=(scoring_tag(courant), score_tag(9), theme_tag("cyber"))),
            make_article("item-2", tags=(scoring_tag(courant), score_tag(2), theme_tag("marche"))),
        ]

        client, scorer, _ = self._run(articles, [])

        scorer.assert_not_called()
        self.assertEqual({}, client.scored)
        # Le score relu des tags pilote quand même la sélection.
        self.assertEqual(["item-1"], client.digested)

    def test_stale_prompt_digest_triggers_rescoring_and_cleanup(self):
        articles = [
            make_article("item-1", tags=(scoring_tag("0123456789ab"), score_tag(2))),
            make_article(
                "item-2",
                tags=(scoring_tag(empreinte()), score_tag(8), theme_tag("cyber")),
            ),
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

    def test_selection_is_grouped_by_thematique(self):
        """Le tri par score seul faisait sauter d'une thématique à l'autre sans transition."""
        articles = [make_article(f"item-{i}") for i in range(4)]
        notes = [
            self.note("item-0", 10, "cyber"),
            self.note("item-1", 9, "reglementaire"),
            self.note("item-2", 8, "cyber"),
            self.note("item-3", 7, "reglementaire"),
        ]

        _, _, digests = self._run(articles, notes)

        # Cyber d'abord : son meilleur article est le meilleur du lot. Le score reste
        # décroissant à l'intérieur de chaque groupe.
        self.assertEqual(
            ["item-0", "item-2", "item-1", "item-3"],
            [a.item_id for a in digests[0].selected],
        )

    def test_the_cap_is_applied_on_the_score_not_on_the_grouping(self):
        """La thématique décide de l'ordre, jamais de qui entre dans le digest."""
        articles = [make_article(f"item-{i}") for i in range(3)]
        notes = [
            self.note("item-0", 10, "cyber"),
            self.note("item-1", 9, "cyber"),
            self.note("item-2", 8, "reglementaire"),
        ]

        _, _, digests = self._run(articles, notes, config_overrides={"max_digest_items": 2})

        self.assertEqual(["item-0", "item-1"], [a.item_id for a in digests[0].selected])

    def test_thematique_and_angle_reach_the_summarizer(self):
        """Ils sont payés par le scoring : les jeter privait le résumé de son contexte."""
        articles = [make_article("item-1")]
        notes = [self.note("item-1", 9, "reglementaire", "Impose une échéance à l'éditeur.")]

        _, _, digests = self._run(articles, notes)

        self.assertEqual(
            Note(9, "reglementaire", "Impose une échéance à l'éditeur."),
            digests[0].new_notes["item-1"],
        )

    def test_thematiques_are_written_to_freshrss(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9, "cyber"), self.note("item-2", 8, "marche")]

        client, _, _ = self._run(articles, notes)

        self.assertEqual({"item-1": "cyber", "item-2": "marche"}, client.themed)

    def test_a_score_without_its_thematique_is_not_a_usable_cache(self):
        """Une note partielle rangerait l'article dans le mauvais groupe : on la renote."""
        courant = empreinte()
        articles = [make_article("item-1", tags=(scoring_tag(courant), score_tag(9)))]

        client, scorer, _ = self._run(articles, [self.note("item-1", 9, "cyber")])

        scorer.assert_called_once()
        self.assertEqual({"item-1": "cyber"}, client.themed)

    def test_threshold_is_read_from_the_config(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 5)]

        _, _, digests = self._run(articles, notes, config_overrides={"score_threshold": 5})

        self.assertEqual(["item-1", "item-2"], sorted(a.item_id for a in digests[0].selected))

    def test_a_category_can_have_its_own_threshold(self):
        """Le généraliste, où tout est intéressant sans être actionnable, se juge à cinq."""
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 6), self.note("item-2", 5)]

        _, _, digests = self._run(
            articles, notes, config_overrides={"category_thresholds": {"tech": 5}}
        )

        self.assertEqual(["item-1", "item-2"], [a.item_id for a in digests[0].selected])

    def test_a_thin_day_falls_back_to_the_lower_threshold(self):
        """Moins de cinq retenus à sept : le seuil du jour tombe à cinq pour tout le monde."""
        articles = [make_article(f"item-{i}") for i in range(6)]
        notes = [self.note(f"item-{i}", score) for i, score in enumerate([9, 8, 7, 6, 5, 4])]

        _, _, digests = self._run(
            articles, notes, config_overrides={"min_digest_items": 5, "fallback_threshold": 5}
        )

        self.assertEqual(
            ["item-0", "item-1", "item-2", "item-3", "item-4"],
            [a.item_id for a in digests[0].selected],
        )

    def test_a_full_day_keeps_its_threshold(self):
        """Cinq articles au-dessus du seuil : rien à replier, les 5-6 restent dehors."""
        articles = [make_article(f"item-{i}") for i in range(6)]
        notes = [self.note(f"item-{i}", score) for i, score in enumerate([10, 9, 8, 7, 7, 6])]

        _, _, digests = self._run(
            articles, notes, config_overrides={"min_digest_items": 5, "fallback_threshold": 5}
        )

        self.assertNotIn("item-5", [a.item_id for a in digests[0].selected])

    def test_the_fallback_does_not_rescue_a_day_that_has_nothing(self):
        """Descendre à cinq ne fabrique pas d'article : la catégorie reste sans sélection."""
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 4), self.note("item-2", 2)]

        client, _, digests = self._run(
            articles, notes, config_overrides={"min_digest_items": 5, "fallback_threshold": 5}
        )

        self.assertEqual([], digests[0].selected)
        self.assertEqual([], client.digested)
        # Le message annonce le seuil réellement appliqué, pas celui de la catégorie.
        self.assertIn("score minimal 5", digests[0].summary_text)

    def test_summary_receives_only_the_selection(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 1)]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"])
            generator = mock.Mock(summarize=mock.Mock(return_value="résumé"))
            DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                scorer=FakeScorer(notes),
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
        self.assertEqual(empreinte(), client.scoring_digest)
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
                make_config(tmpdir), categories=["Tech"])
            client = FakeFreshRSSClient({"Tech": articles})
            sender = FakeEmailSender()
            sender.send = mock.Mock(side_effect=RuntimeError("SMTP down"))
            service = DigestService(
                config=config,
                freshrss_client=client,
                scorer=FakeScorer(notes),
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
                make_config(tmpdir), categories=["Tech", "News"]
            )
            client = FakeFreshRSSClient({"Tech": tech, "News": news})
            # La deuxième catégorie casse : la première ne doit pas perdre ses scores.
            scorer = FakeScorer(
                side_effect=[[self.note("item-1", 9)], RuntimeError("API down")]
            )

            with self.assertRaises(RuntimeError):
                DigestService(
                    config=config,
                    freshrss_client=client,
                    scorer=scorer,
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


class NoSelectionMarkerTests(unittest.TestCase):
    """Aucun article au-dessus du seuil : marqueur listant les scores, pas d'audio."""

    def _run(self, articles, notes):
        """Renvoie (digest, contenu du marqueur, générateurs) — lus avant le nettoyage du tmpdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"]
            )
            summary_generator = mock.Mock()
            audio_generator = mock.Mock()
            digests = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                scorer=FakeScorer(notes),
                summary_generator=summary_generator,
                audio_generator=audio_generator,
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)
            marker = digests[0].marker_path
            return digests[0], marker.read_text(encoding="utf-8"), summary_generator, audio_generator

    def test_marker_replaces_the_audio_and_lists_the_scores(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [{"id": "item-1", "score": 3, "thematique": "cyber", "angle": "a"},
                 {"id": "item-2", "score": 5, "thematique": "cyber", "angle": "a"}]

        digest, contenu, summary_generator, audio_generator = self._run(articles, notes)

        self.assertIsNone(digest.audio_path)
        self.assertEqual("tech.no-article", digest.marker_path.name)
        # Ni résumé ni synthèse vocale : c'est tout l'intérêt du marqueur.
        summary_generator.summarize.assert_not_called()
        audio_generator.synthesize.assert_not_called()
        # Les scores, les meilleurs d'abord, pour juger le seuil sans ouvrir FreshRSS.
        self.assertEqual(
            [
                "Aucun article retenu sur 2 (seuil 7).",
                "",
                " 5/10 cyber         - Titre item-2",
                " 3/10 cyber         - Titre item-1",
            ],
            contenu.splitlines(),
        )

    def test_scores_are_still_cached_in_freshrss(self):
        """Sans cela, un lot entièrement sous le seuil serait renoté chaque jour."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 2, "thematique": "autre", "angle": "a"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"]
            )
            client = FakeFreshRSSClient({"Tech": articles})
            DigestService(
                config=config,
                freshrss_client=client,
                scorer=FakeScorer(notes),
                summary_generator=mock.Mock(),
                audio_generator=mock.Mock(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)

        self.assertEqual({"item-1": 2}, client.scored)
        self.assertEqual(empreinte(), client.scoring_digest)
        self.assertEqual([], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])


if __name__ == "__main__":
    unittest.main()
