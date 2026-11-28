"""Intégration du scoring dans le pipeline : cache par empreinte de prompt et sélection."""

import dataclasses
import datetime as dt
import tempfile
import unittest
from unittest import mock

from rssresume.digest import DigestService
from rssresume.models import Article, Note
from tests.support import (
    FakeAudioGenerator,
    FakeCacheScoring,
    FakeEmailSender,
    FakeFreshRSSClient,
    FakeScorer,
    empreinte,
    make_config,
)

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

    def _run(self, articles, notes, config_overrides=None, cache=None, **kwargs):
        """Exécute le pipeline avec un scoring simulé ; le cache est exposé à `self.cache`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir),
                categories=["Tech"],
                **(config_overrides or {}),
            )
            client = FakeFreshRSSClient({"Tech": articles})
            scorer = FakeScorer(notes)
            self.cache = cache if cache is not None else FakeCacheScoring()
            digests = DigestService(
                config=config,
                freshrss_client=client,
                scorer=scorer,
                cache_scoring=self.cache,
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False, **kwargs)
            return client, scorer.score_articles, digests

    def _summarize_call(self, articles, notes, cache=None):
        """L'appel réellement reçu par le résumeur : (catégorie, sélection, notes)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(tmpdir), categories=["Tech"])
            generator = mock.Mock(summarize=mock.Mock(return_value="résumé"))
            self.cache = cache if cache is not None else FakeCacheScoring()
            DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                scorer=FakeScorer(notes),
                cache_scoring=self.cache,
                summary_generator=generator,
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)
            return generator.summarize.call_args.args

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

    def test_scores_are_written_to_the_cache_with_the_prompt_digest(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 3)]

        self._run(articles, notes)

        courant = empreinte()
        self.assertEqual(
            [("item-1", courant, Note(9, "cyber", "a")), ("item-2", courant, Note(3, "cyber", "a"))],
            self.cache.enregistrements,
        )

    def test_already_scored_articles_are_not_rescored(self):
        courant = empreinte()
        cache = FakeCacheScoring()
        cache.enregistrer("item-1", courant, Note(9, "cyber", "un angle"))
        cache.enregistrer("item-2", courant, Note(2, "marche", ""))
        articles = [make_article("item-1"), make_article("item-2")]

        client, scorer, _ = self._run(articles, [], cache=cache)

        scorer.assert_not_called()
        # Le score relu du cache pilote quand même la sélection.
        self.assertEqual(["item-1"], client.digested)
        # Et le cache n'est pas réécrit.
        self.assertEqual(2, len(cache.enregistrements))

    def test_an_old_fingerprint_triggers_rescoring(self):
        """Une empreinte différente est un cache manqué : renoté, sans rien nettoyer."""
        cache = FakeCacheScoring()
        cache.enregistrer("item-1", "0123456789ab", Note(2, "cyber", ""))
        cache.enregistrer("item-2", empreinte(), Note(8, "cyber", ""))
        articles = [make_article("item-1"), make_article("item-2")]

        client, scorer, _ = self._run(articles, [self.note("item-1", 9)], cache=cache)

        scorer.assert_called_once()
        self.assertEqual(["item-1"], [a["id"] for a in scorer.call_args.args[0]])
        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", empreinte()))
        # item-2, relu du cache à 8, est retenu lui aussi.
        self.assertEqual(["item-1", "item-2"], client.digested)

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

    def test_at_equal_best_score_the_first_group_stays_ahead(self):
        """Le tri des groupes est stable : deux groupes ex aequo gardent l'ordre du score."""
        articles = [make_article(f"item-{i}") for i in range(4)]
        notes = [
            self.note("item-0", 9, "cyber"),
            self.note("item-1", 9, "reglementaire"),
            self.note("item-2", 8, "reglementaire"),
            self.note("item-3", 7, "cyber"),
        ]

        _, _, digests = self._run(articles, notes)

        # Les deux groupes ouvrent à 9 : c'est cyber, arrivé le premier, qui passe devant.
        # L'ordre vient des scores du jour, jamais d'une liste de thématiques figée.
        self.assertEqual(
            ["item-0", "item-3", "item-1", "item-2"],
            [a.item_id for a in digests[0].selected],
        )

    def test_the_autre_theme_is_placed_like_any_other(self):
        """« autre » n'est pas reléguée : elle est classée sur son meilleur article, comme les autres."""
        articles = [make_article(f"item-{i}") for i in range(3)]
        notes = [
            self.note("item-0", 9, "autre"),
            self.note("item-1", 8, "reglementaire"),
            self.note("item-2", 7, "autre"),
        ]

        _, _, digests = self._run(articles, notes)

        self.assertEqual(
            ["item-0", "item-2", "item-1"], [a.item_id for a in digests[0].selected]
        )

    def test_an_article_without_a_note_falls_into_the_autre_group(self):
        """Un article entré sans note se range, faute de thématique, avec les « autre ».

        Le repli à zéro est le seul chemin qui les laisse entrer malgré tout. `_note_of`
        leur prête une note neutre, dont la thématique par défaut est « autre » : le
        regroupement n'a aucun cas particulier à connaître, et ne lève pas.
        """
        articles = [make_article(f"item-{i}") for i in range(3)]
        notes = [
            self.note("item-0", 9, "cyber"),
            {"id": "item-1", "score": 0, "thematique": "autre", "angle": "", "notee": False},
            self.note("item-2", 8, "cyber"),
        ]

        _, _, digests = self._run(
            articles,
            notes,
            config_overrides={"min_digest_items": 5, "fallback_threshold": 0},
        )

        self.assertEqual(
            ["item-0", "item-2", "item-1"], [a.item_id for a in digests[0].selected]
        )

    def test_thematique_and_angle_reach_the_summarizer(self):
        """Ils sont payés par le scoring : les jeter privait le résumé de son contexte."""
        articles = [make_article("item-1")]
        notes = [self.note("item-1", 9, "reglementaire", "Impose une échéance à l'éditeur.")]

        _, _, digests = self._run(articles, notes)

        self.assertEqual(
            Note(9, "reglementaire", "Impose une échéance à l'éditeur."),
            digests[0].new_notes["item-1"],
        )

    def test_the_whole_note_is_handed_to_the_summarizer(self):
        """Le maillon suivant : `_score` ne remontait que {id: score}, et s'arrêtait là."""
        _, _, notes = self._summarize_call(
            [make_article("item-1")],
            [self.note("item-1", 9, "reglementaire", "Impose une échéance à l'éditeur.")],
        )

        self.assertEqual(
            {"item-1": Note(9, "reglementaire", "Impose une échéance à l'éditeur.")}, notes
        )

    def test_a_note_reread_from_the_cache_keeps_its_angle(self):
        """L'angle est persisté dans le cache : une note relue revient entière."""
        cache = FakeCacheScoring()
        cache.enregistrer("item-1", empreinte(), Note(9, "cyber", "Menace sur la stack."))
        articles = [make_article("item-1")]

        _, _, notes = self._summarize_call(articles, [], cache=cache)

        self.assertEqual({"item-1": Note(9, "cyber", "Menace sur la stack.")}, notes)

    def test_thematiques_are_written_to_the_cache(self):
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9, "cyber"), self.note("item-2", 8, "marche")]

        self._run(articles, notes)

        courant = empreinte()
        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", courant))
        self.assertEqual(Note(8, "marche", "a"), self.cache.note("item-2", courant))

    def test_a_cached_note_outside_the_axes_is_rescored(self):
        """Une thématique qui n'est plus un axe du profil rangerait l'article dans le
        mauvais groupe : la note en cache est traitée comme absente."""
        cache = FakeCacheScoring()
        cache.enregistrer("item-1", empreinte(), Note(9, "inconnu", ""))
        articles = [make_article("item-1")]

        _, scorer, _ = self._run(articles, [self.note("item-1", 9, "cyber")], cache=cache)

        scorer.assert_called_once()
        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", empreinte()))

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

    def test_dry_run_writes_nothing(self):
        """--dry-run n'écrit ni dans le cache de scoring ni dans FreshRSS."""
        articles = [make_article("item-1")]

        client, _, _ = self._run(
            articles, [self.note("item-1", 9)], write_tags=False, mark_read=False
        )

        self.assertEqual([], self.cache.enregistrements)
        self.assertEqual([], client.digested)
        self.assertEqual([], client.marked_as_read)


class WriteFlagsTests(PipelineHarness, unittest.TestCase):
    """Les deux axes d'écriture FreshRSS sont indépendants."""

    def test_no_mark_read_still_writes_the_score_cache(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)], mark_read=False)

        # C'est l'intérêt du découpage : le scoring n'est pas repayé au prochain essai.
        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", empreinte()))
        self.assertEqual(["item-1"], client.digested)
        self.assertEqual([], client.marked_as_read)

    def test_no_tags_still_marks_articles_as_read(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)], write_tags=False)

        self.assertEqual([], self.cache.enregistrements)
        self.assertEqual([], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])

    def test_cache_survives_an_email_failure(self):
        """Les notes sont ecrites dans le cache par categorie, avant l'envoi."""
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [self.note("item-1", 9), self.note("item-2", 2)]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"])
            client = FakeFreshRSSClient({"Tech": articles})
            cache = FakeCacheScoring()
            sender = FakeEmailSender()
            sender.send = mock.Mock(side_effect=RuntimeError("SMTP down"))
            service = DigestService(
                config=config,
                freshrss_client=client,
                scorer=FakeScorer(notes),
                cache_scoring=cache,
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="r")),
                audio_generator=FakeAudioGenerator(),
                email_sender=sender,
            )
            with self.assertRaises(RuntimeError):
                service.run(DAY)

        # Notes et tag digest conserves : le prochain passage ne repaie pas le scoring.
        courant = empreinte()
        self.assertEqual(Note(9, "cyber", "a"), cache.note("item-1", courant))
        self.assertEqual(Note(2, "cyber", "a"), cache.note("item-2", courant))
        self.assertEqual(["item-1"], client.digested)
        # Le marquage comme lu, lui, n'a pas eu lieu : les articles seront repris.
        self.assertEqual([], client.marked_as_read)

    def test_cache_of_earlier_categories_survives_a_later_failure(self):
        """Une categorie qui casse ne fait pas perdre les scores des precedentes."""
        tech = [make_article("item-1")]
        news = [make_article("item-2")]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech", "News"]
            )
            client = FakeFreshRSSClient({"Tech": tech, "News": news})
            cache = FakeCacheScoring()
            # La deuxième catégorie casse : la première ne doit pas perdre ses scores.
            scorer = FakeScorer(
                side_effect=[[self.note("item-1", 9)], RuntimeError("API down")]
            )

            with self.assertRaises(RuntimeError):
                DigestService(
                    config=config,
                    freshrss_client=client,
                    scorer=scorer,
                    cache_scoring=cache,
                    summary_generator=mock.Mock(summarize=mock.Mock(return_value="r")),
                    audio_generator=FakeAudioGenerator(),
                    email_sender=FakeEmailSender(),
                ).run(DAY, send_email=False)

        self.assertEqual(Note(9, "cyber", "a"), cache.note("item-1", empreinte()))
        self.assertEqual(["item-1"], client.digested)

    def test_default_run_writes_everything(self):
        articles = [make_article("item-1")]

        client, _, _ = self._run(articles, [self.note("item-1", 9)])

        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", empreinte()))
        self.assertEqual(["item-1"], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])


class DegradedScoringTests(PipelineHarness, unittest.TestCase):
    """Un article que le modèle a sauté : écarté du jour, jamais figé dans un tag.

    Le lot incomplet ne fait plus tomber la catégorie ; il ne doit pas non plus laisser
    un `score-00` derrière lui, qui servirait de cache à toutes les exécutions suivantes.
    """

    @staticmethod
    def sans_note(item_id):
        """La note de remplissage que rend `read_scores` pour un article oublié."""
        return {"id": item_id, "score": 0, "thematique": "autre", "angle": "", "notee": False}

    def test_an_unscored_article_is_neither_cached_nor_digested(self):
        articles = [make_article("item-1"), make_article("item-2")]

        client, _, digests = self._run(
            articles, [self.note("item-1", 9), self.sans_note("item-2")]
        )

        courant = empreinte()
        self.assertEqual(Note(9, "cyber", "a"), self.cache.note("item-1", courant))
        self.assertIsNone(self.cache.note("item-2", courant))
        self.assertEqual(["item-1"], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in digests[0].selected])

    def test_the_rest_of_the_batch_is_scored_as_usual(self):
        """C'est tout l'intérêt : la catégorie sort, amputée d'un article et non perdue."""
        articles = [make_article("item-1"), make_article("item-2")]

        _, _, digests = self._run(articles, [self.sans_note("item-1"), self.note("item-2", 8)])

        self.assertIsNotNone(digests[0].audio_path)

    def test_a_category_whose_scoring_lost_everything_yields_no_audio(self):
        """Sans une seule note, la journée est vide, surtout pas racontée sans avoir été triée."""
        articles = [make_article("item-1"), make_article("item-2")]

        client, _, digests = self._run(articles, [self.sans_note("item-1"), self.sans_note("item-2")])

        self.assertEqual([], self.cache.enregistrements)
        self.assertEqual([], digests[0].selected)
        self.assertIsNone(digests[0].audio_path)


class NoScorerGroupingTests(unittest.TestCase):
    """Aucune API de scoring : tout entre sans note, et le regroupement doit tenir.

    C'est le seul chemin où `_grouped_by_theme` ne reçoit que des notes neutres. Il ne
    forme alors qu'un groupe, et ne doit surtout pas réordonner ce que la journée a lu.
    """

    def _run(self, articles):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(tmpdir), categories=["Tech"])
            return DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)

    def test_every_article_lands_in_the_same_group_in_the_order_read(self):
        articles = [make_article(f"item-{i}") for i in range(3)]

        digests = self._run(articles)

        self.assertEqual(
            ["item-0", "item-1", "item-2"], [a.item_id for a in digests[0].selected]
        )

    def test_the_category_is_still_summarized_and_voiced(self):
        """Sans seuil ni note, la journée sort quand même : c'est le repli sans clé d'API."""
        digests = self._run([make_article("item-1")])

        self.assertIsNotNone(digests[0].audio_path)


class NoSelectionMarkerTests(unittest.TestCase):
    """Aucun article au-dessus du seuil : marqueur listant les scores, pas d'audio."""

    def _run(self, articles, notes):
        """Renvoie (digest, contenu du marqueur, générateurs), lus avant le nettoyage du tmpdir."""
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

    def test_scores_are_still_written_to_the_cache(self):
        """Sans cela, un lot entièrement sous le seuil serait renoté chaque jour."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 2, "thematique": "autre", "angle": "a"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=["Tech"]
            )
            client = FakeFreshRSSClient({"Tech": articles})
            cache = FakeCacheScoring()
            DigestService(
                config=config,
                freshrss_client=client,
                scorer=FakeScorer(notes),
                cache_scoring=cache,
                summary_generator=mock.Mock(),
                audio_generator=mock.Mock(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False)

        self.assertEqual(Note(2, "autre", "a"), cache.note("item-1", empreinte()))
        self.assertEqual([], client.digested)
        self.assertEqual(["item-1"], [a.item_id for a in client.marked_as_read])


if __name__ == "__main__":
    unittest.main()
