"""Le cache de scoring en SQLite : persistance des notes, et tests d'acceptation.

Le cache vit dans la base des profils (`RSSRESUME_PROFILES_DB`), table `scores`,
clé (item_id, empreinte) -> score, thematique, angle. L'angle est persisté. Deux
profils au texte identique partagent la même empreinte, donc la même note.
"""

import dataclasses
import datetime as dt
import pathlib
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

from rssresume.cache_scoring import CacheScoringSqlite
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.models import Article, Note
from rssresume.profil import Lecteur, Profil, nouvel_id
from tests.support import (
    FakeAudioGenerator,
    FakeEmailSender,
    FakeFreshRSSClient,
    FakeScorer,
    empreinte,
    make_config,
)

DAY = dt.date(2026, 8, 23)


def _lire(chemin, requete):
    """Une requête en lecture sur la base, connexion refermée aussitôt."""
    connexion = sqlite3.connect(chemin)
    try:
        return connexion.execute(requete).fetchall()
    finally:
        connexion.close()


def make_article(item_id, category="Tech"):
    return Article(
        item_id=item_id,
        category=category,
        title=f"Titre {item_id}",
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text="Contenu de l'article.",
    )


def make_service(output_dir, articles, scorer, cache_scoring, config_overrides=None, summarizer=None):
    """Un DigestService sur une catégorie « Tech », cache injecté."""
    config = dataclasses.replace(
        make_config(output_dir), categories=["Tech"], **(config_overrides or {})
    )
    return DigestService(
        config=config,
        freshrss_client=FakeFreshRSSClient({"Tech": articles}),
        scorer=scorer,
        cache_scoring=cache_scoring,
        summary_generator=summarizer or mock.Mock(summarize=mock.Mock(return_value="résumé")),
        audio_generator=FakeAudioGenerator(),
        email_sender=FakeEmailSender(),
    ), config


class CacheScoringSqliteTests(unittest.TestCase):
    """Le cache seul : lecture, écriture, clé primaire, angle persisté."""

    def test_une_note_absente_renvoie_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")

            self.assertIsNone(cache.note("item-1", "abc"))

    def test_enregistrer_puis_note_renvoie_la_note_entiere_angle_compris(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")

            cache.enregistrer("item-1", "abc", Note(9, "cyber", "Menace sur la stack."))

            self.assertEqual(Note(9, "cyber", "Menace sur la stack."), cache.note("item-1", "abc"))

    def test_deux_empreintes_coexistent_pour_le_meme_article(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")

            cache.enregistrer("item-1", "ancien", Note(2, "autre", ""))
            cache.enregistrer("item-1", "courant", Note(9, "cyber", "a"))

            self.assertEqual(Note(2, "autre", ""), cache.note("item-1", "ancien"))
            self.assertEqual(Note(9, "cyber", "a"), cache.note("item-1", "courant"))

    def test_reenregistrer_la_meme_cle_remplace_la_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")

            cache.enregistrer("item-1", "abc", Note(2, "autre", ""))
            cache.enregistrer("item-1", "abc", Note(7, "marche", "b"))

            self.assertEqual(Note(7, "marche", "b"), cache.note("item-1", "abc"))
            self.assertEqual(
                [(1,)], _lire(pathlib.Path(tmpdir) / "profils.sqlite3", "SELECT COUNT(*) FROM scores")
            )

    def test_la_table_scores_est_creee_dans_la_base(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "profils.sqlite3"
            CacheScoringSqlite(chemin)

            colonnes = _lire(chemin, "PRAGMA table_info(scores)")

            self.assertEqual(
                ["item_id", "empreinte", "score", "thematique", "angle"],
                [colonne[1] for colonne in colonnes],
            )
            self.assertEqual(
                {"item_id", "empreinte"},
                {colonne[1] for colonne in colonnes if colonne[5]},
            )


class AcceptationCacheTests(unittest.TestCase):
    """Les tests d'acceptation du cache, bout en bout avec la vraie base SQLite."""

    def _run(self, tmpdir, articles, notes, cache, config_overrides=None, scorer=None, **kwargs):
        """Lance le digest sur « Tech » ; renvoie (service, client, scorer, config)."""
        service, config = make_service(
            pathlib.Path(tmpdir) / "out",
            articles,
            scorer or FakeScorer(notes),
            cache,
            config_overrides=config_overrides,
        )
        digests = service.run(DAY, send_email=False, **kwargs)
        return digests, service._freshrss_client, service._scorer.score_articles, config

    def test_a_article_deja_note_sous_la_meme_empreinte_est_relu_du_cache(self):
        """(a) Non renvoyé au modèle, et la note revenue porte thème et angle."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 9, "thematique": "cyber", "angle": "Menace sur la stack."}]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")
            self._run(tmpdir, articles, notes, cache)

            # Second passage, même base, nouveau noteur et nouveau résumeur.
            deuxieme_scorer = FakeScorer([])
            summarizer = mock.Mock(summarize=mock.Mock(return_value="résumé"))
            service, _ = make_service(
                pathlib.Path(tmpdir) / "out2", articles, deuxieme_scorer, cache, summarizer=summarizer
            )
            service.run(DAY, send_email=False)

            deuxieme_scorer.score_articles.assert_not_called()
            recu = summarizer.summarize.call_args.args[2]
            self.assertEqual(
                {"item-1": Note(9, "cyber", "Menace sur la stack.")}, recu
            )

    def test_b_une_empreinte_differente_renote(self):
        """(b) Profil changé, empreinte changée : le cache manque, le modèle repart."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 9, "thematique": "cyber", "angle": "a"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")
            self._run(tmpdir, articles, notes, cache)

            deuxieme_scorer = FakeScorer(notes)
            service, _ = make_service(
                pathlib.Path(tmpdir) / "out2",
                articles,
                deuxieme_scorer,
                cache,
                config_overrides={"profil": "Un tout autre profil de pertinence."},
            )
            service.run(DAY, send_email=False)

            deuxieme_scorer.score_articles.assert_called_once()
            # Les deux empreintes coexistent : l'ancienne note n'est pas écrasée.
            self.assertIsNotNone(cache.note("item-1", empreinte()))
            self.assertIsNotNone(
                cache.note("item-1", empreinte("Un tout autre profil de pertinence."))
            )

    def test_c_aucun_libelle_score_theme_scoring_n_est_plus_pose(self):
        """(c) Seul `digested` part encore vers FreshRSS."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 9, "thematique": "cyber", "angle": "a"}]
        motif_scoring = re.compile(r"(?:^|-)(score|theme|scoring)-")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(make_config(pathlib.Path(tmpdir) / "out"), categories=["Tech"])
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")

            class ClientEspion(FreshRSSClient):
                """Le vrai client, dont on espionne les labels sans rien poster."""

                def __init__(self):
                    super().__init__(config)
                    self.labels = []

                def fetch_daily_articles(self, category, day):
                    return list(articles)

                def add_label(self, item_ids, label):
                    self.labels.append(label)

            client = ClientEspion()
            DigestService(
                config=config,
                freshrss_client=client,
                scorer=FakeScorer(notes),
                cache_scoring=cache,
                summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            ).run(DAY, send_email=False, mark_read=False)

            self.assertEqual(["digested"], client.labels)
            self.assertEqual([], [l for l in client.labels if motif_scoring.search(l)])

    def test_d_deux_profils_au_texte_identique_ne_notent_qu_une_fois(self):
        """(d) Même empreinte, même note : le second profil ne repasse pas au modèle."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 9, "thematique": "cyber", "angle": "a"}]
        texte_identique = "CTO d'un SaaS B2B, veille sur le cloud et la cybersécurité."

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")
            scorer = FakeScorer(notes)
            base = make_config(pathlib.Path(tmpdir) / "out")

            for username in ("adrien", "bea"):
                lecteur = Lecteur(username, Profil(texte_identique, identifiant=nouvel_id()))
                config = dataclasses.replace(base.pour(lecteur), categories=["Tech"])
                service = DigestService(
                    config=config,
                    freshrss_client=FakeFreshRSSClient({"Tech": articles}),
                    scorer=scorer,
                    cache_scoring=cache,
                    summary_generator=mock.Mock(summarize=mock.Mock(return_value="résumé")),
                    audio_generator=FakeAudioGenerator(),
                    email_sender=FakeEmailSender(),
                )
                service.run(DAY, send_email=False)

            # Une seule notation pour les deux profils au texte identique.
            scorer.score_articles.assert_called_once()
            self.assertEqual(
                Note(9, "cyber", "a"),
                cache.note("item-1", empreinte(texte_identique)),
            )

    def test_e_dry_run_n_ecrit_rien_dans_la_base(self):
        """(e) --dry-run : la table `scores` reste vide."""
        articles = [make_article("item-1")]
        notes = [{"id": "item-1", "score": 9, "thematique": "cyber", "angle": "a"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "profils.sqlite3"
            cache = CacheScoringSqlite(chemin)
            self._run(tmpdir, articles, notes, cache, write_tags=False, mark_read=False)

            self.assertEqual(
                [(0,)], _lire(chemin, "SELECT COUNT(*) FROM scores")
            )

    def test_f_relancer_une_journee_ne_recoûte_pas_le_scoring(self):
        """(f) Deux passages sur la même journée, même base : un seul appel au modèle."""
        articles = [make_article("item-1"), make_article("item-2")]
        notes = [
            {"id": "item-1", "score": 9, "thematique": "cyber", "angle": "a"},
            {"id": "item-2", "score": 8, "thematique": "marche", "angle": "b"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheScoringSqlite(pathlib.Path(tmpdir) / "profils.sqlite3")
            self._run(tmpdir, articles, notes, cache)

            deuxieme_scorer = FakeScorer([])
            self._run(tmpdir, articles, [], cache, scorer=deuxieme_scorer)

            deuxieme_scorer.score_articles.assert_not_called()


if __name__ == "__main__":
    unittest.main()
