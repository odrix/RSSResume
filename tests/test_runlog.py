"""Journal d'exécution : contenu du `.log.json` et rattachement des appels à la catégorie."""

import dataclasses
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import runlog
from rssresume.audio import AudioGenerator
from rssresume.digest import DigestService
from rssresume.llm.openai import OpenAIProvider
from rssresume.models import Article, Note
from rssresume.llm.providers import Settings, Voice
from support import FakeEmailSender, FakeFreshRSSClient, FakeScorer, make_config

DAY = dt.date(2026, 8, 26)

#: Réponse minimale du fournisseur, compteurs de tokens compris.
USAGE = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}


def make_article(item_id="item-1", title="Titre"):
    return Article(
        item_id=item_id,
        category="Tech",
        title=title,
        url=f"https://example.com/{item_id}",
        published_at=dt.datetime(2026, 8, 26, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="Feed",
        content_text="Contenu de l'article.",
    )


def journal(tmpdir, category="Tech", slug="tech"):
    return runlog.CategoryJournal(category, slug, DAY, pathlib.Path(tmpdir))


class CostAggregationTests(unittest.TestCase):
    """Les trois postes demandés : somme des scorings, des résumés, de la synthèse vocale."""

    def _couts(self, remplir):
        with tempfile.TemporaryDirectory() as tmpdir:
            book = journal(tmpdir)
            remplir(book)
            return book.as_json()["couts"]

    def test_calls_are_summed_under_their_typologie(self):
        def remplir(book):
            book.record_chat("scoring", "gpt-4o-mini", USAGE)
            book.record_chat("scoring", "gpt-4o-mini", USAGE)
            book.record_chat("digest", "gpt-4o-mini", USAGE)
            book.record_tts("tts-1", "alloy", "a" * 1000)

        couts = self._couts(remplir)

        self.assertEqual(2, couts["par_typologie"]["scoring"]["appels"])
        self.assertEqual(1, couts["par_typologie"]["resume"]["appels"])
        self.assertEqual(1, couts["par_typologie"]["tts"]["appels"])
        self.assertEqual(2000, couts["par_typologie"]["scoring"]["tokens_entree"])
        self.assertEqual(1000, couts["par_typologie"]["tts"]["caracteres"])

    def test_the_article_summary_counts_as_a_resume(self):
        """Résumé par article et digest de catégorie sont deux façons de résumer."""
        couts = self._couts(lambda book: book.record_chat("article summary", "gpt-4o-mini", USAGE))

        self.assertEqual(1, couts["par_typologie"]["resume"]["appels"])
        self.assertEqual(0, couts["par_typologie"]["scoring"]["appels"])

    def test_the_total_is_the_sum_of_the_typologies(self):
        def remplir(book):
            book.record_chat("scoring", "gpt-4o-mini", USAGE)
            book.record_chat("digest", "gpt-4o", USAGE)
            book.record_tts("tts-1", "alloy", "a" * 1000)

        couts = self._couts(remplir)

        somme = sum(poste["cout"] for poste in couts["par_typologie"].values())
        # Chaque poste est arrondi pour l'affichage : la somme des trois peut
        # s'écarter du total d'un cheveu, jamais davantage.
        self.assertAlmostEqual(somme, couts["total"], places=5)
        self.assertTrue(couts["tarification_complete"])

    def test_reasoning_tokens_are_isolated(self):
        """Ils sont inclus dans les tokens de sortie, mais expliquent seuls certaines factures."""
        usage = {**USAGE, "completion_tokens_details": {"reasoning_tokens": 400}}

        couts = self._couts(lambda book: book.record_chat("digest", "gpt-5-mini", usage))

        self.assertEqual(400, couts["par_typologie"]["resume"]["tokens_raisonnement"])
        self.assertEqual(500, couts["par_typologie"]["resume"]["tokens_sortie"])

    def test_an_untarifed_model_is_named_and_flagged(self):
        """Un total amputé d'un modèle inconnu se lirait sinon comme un total."""
        couts = self._couts(lambda book: book.record_chat("digest", "modele-maison", USAGE))

        self.assertFalse(couts["tarification_complete"])
        self.assertEqual(["modele-maison"], couts["modeles_sans_tarif"])
        self.assertIsNone(couts["appels"][0]["cout"])

    def test_an_untarifed_call_voids_its_total_rather_than_shrinking_it(self):
        """Une somme partielle est un chiffre que quelqu'un reportera dans un tableur."""

        def remplir(book):
            book.record_chat("scoring", "gpt-4o-mini", USAGE)
            book.record_chat("digest", "modele-maison", USAGE)

        couts = self._couts(remplir)

        self.assertIsNone(couts["total"])
        self.assertIsNone(couts["par_typologie"]["resume"]["cout"])
        # Le poste entièrement tarifé, lui, garde son coût.
        self.assertGreater(couts["par_typologie"]["scoring"]["cout"], 0)

    def test_a_poste_without_any_call_costs_zero_not_null(self):
        """Rien dépensé et coût inconnu ne se lisent pas pareil."""
        couts = self._couts(lambda book: book.record_chat("scoring", "gpt-4o-mini", USAGE))

        self.assertEqual(0.0, couts["par_typologie"]["tts"]["cout"])

    def test_a_missing_usage_block_does_not_break_the_journal(self):
        """Tous les fournisseurs compatibles ne renvoient pas `usage`."""
        couts = self._couts(lambda book: book.record_chat("digest", "gpt-4o-mini", None))

        self.assertEqual(0, couts["par_typologie"]["resume"]["tokens_entree"])
        self.assertEqual(0.0, couts["total"])

    def test_a_character_billed_tts_reports_no_tokens(self):
        couts = self._couts(lambda book: book.record_tts("tts-1", "alloy", "a" * 1000))

        appel = couts["appels"][0]
        self.assertEqual(0, appel["tokens_entree"])
        self.assertEqual(1000, appel["caracteres"])
        self.assertNotIn("cout_estime", appel)

    def test_a_token_billed_tts_marks_its_cost_as_estimated(self):
        """La synthèse ne rend aucun compteur : les tokens y sont déduits du texte."""
        couts = self._couts(lambda book: book.record_tts("gpt-4o-mini-tts", "alloy", "a" * 1000))

        self.assertTrue(couts["appels"][0]["cout_estime"])
        self.assertEqual(250, couts["appels"][0]["tokens_entree"])


class ScopeTests(unittest.TestCase):
    def test_nothing_is_recorded_outside_a_scope(self):
        """`processing.py` lancé seul ne doit rien écrire."""
        self.assertIsNone(runlog.active())
        runlog.record_chat("digest", "gpt-4o-mini", USAGE)
        runlog.record_tts("tts-1", "alloy", "texte")

    def test_the_journal_is_written_even_when_the_category_fails(self):
        """C'est le cas où il sert le plus, y compris sans article récupéré."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                with runlog.category_scope("Tech", "tech", DAY, pathlib.Path(tmpdir)) as book:
                    book.record_chat("scoring", "gpt-4o-mini", USAGE)
                    raise RuntimeError("le fournisseur a lâché")

            ecrit = json.loads((pathlib.Path(tmpdir) / "tech.log.json").read_text(encoding="utf-8"))
            self.assertEqual("interrompu", ecrit["resultat"]["statut"])
            self.assertEqual(1, ecrit["couts"]["par_typologie"]["scoring"]["appels"])

    def test_leaving_the_scope_stops_the_recording(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with runlog.category_scope("Tech", "tech", DAY, pathlib.Path(tmpdir)):
                pass
            self.assertIsNone(runlog.active())


class ArticleListingTests(unittest.TestCase):
    def _articles(self, articles, notes, new_notes, selected):
        with tempfile.TemporaryDirectory() as tmpdir:
            book = journal(tmpdir)
            book.set_notes(notes, new_notes)
            book.set_digest(
                mock.Mock(articles=articles, selected=selected, audio_path=None, marker_path=None)
            )
            return book.as_json()["articles"]

    def test_every_article_is_listed_best_scored_first(self):
        """Le journal sert à juger le seuil : il faut voir ce qui est passé à côté."""
        articles = [make_article("a"), make_article("b"), make_article("c")]
        notes = {"a": Note(3, "marche"), "b": Note(9, "cyber"), "c": Note(6, "stack")}

        listing = self._articles(articles, notes, notes, [articles[1]])

        self.assertEqual(["b", "c", "a"], [entree["item_id"] for entree in listing])
        self.assertEqual([9, 6, 3], [entree["score"] for entree in listing])

    def test_the_selection_is_marked_with_its_reading_order(self):
        articles = [make_article("a"), make_article("b")]
        notes = {"a": Note(9, "cyber", "angle a"), "b": Note(2, "autre")}

        listing = self._articles(articles, notes, notes, [articles[0]])

        retenu, ecarte = listing
        self.assertTrue(retenu["retenu"])
        self.assertEqual(1, retenu["rang_digest"])
        self.assertEqual("angle a", retenu["angle"])
        self.assertFalse(ecarte["retenu"])
        self.assertIsNone(ecarte["rang_digest"])

    def test_a_note_read_from_the_tags_is_told_apart_from_a_fresh_one(self):
        """Une note relue des tags n'a pas d'angle : le journal doit dire pourquoi."""
        articles = [make_article("a"), make_article("b")]
        notes = {"a": Note(9, "cyber"), "b": Note(8, "cyber", "angle b")}

        listing = self._articles(articles, notes, {"b": notes["b"]}, articles)

        origines = {entree["item_id"]: entree["origine_note"] for entree in listing}
        self.assertEqual({"a": "tags", "b": "calculee"}, origines)

    def test_articles_without_scoring_are_listed_without_a_note(self):
        articles = [make_article("a")]

        listing = self._articles(articles, {}, {}, articles)

        self.assertIsNone(listing[0]["score"])
        self.assertEqual("aucune", listing[0]["origine_note"])


class PipelineTests(unittest.TestCase):
    """Le journal tel qu'il sort d'une exécution complète."""

    def _run(self, articles_by_category, **overrides):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir), categories=list(articles_by_category), **overrides
            )
            # Un vrai fournisseur pour la synthèse — c'est lui qui tient la comptabilité
            # du TTS ; seul son POST est coupé. Le noteur et le résumeur sont simulés,
            # et facturent à la main ce que le vrai facturerait.
            voix = OpenAIProvider(
                Settings(
                    name="openai",
                    label="OpenAI",
                    base_url="https://api.example/v1",
                    api_key="key",
                    calls={},
                    voice=Voice(model="tts-1", voice="alloy"),
                    prices={},
                )
            )
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient(articles_by_category),
                scorer=FakeScorer(side_effect=self._fake_scoring),
                summary_generator=mock.Mock(summarize=self._fake_summary),
                audio_generator=AudioGenerator(voix),
                email_sender=FakeEmailSender(),
            )
            with mock.patch.object(OpenAIProvider, "_post", return_value=b"audio"):
                service.run(DAY, send_email=False, write_tags=False, mark_read=False)
            day_dir = pathlib.Path(tmpdir) / DAY.isoformat()
            return {
                path.name: json.loads(path.read_text(encoding="utf-8"))
                for path in day_dir.glob(f"*{runlog.LOG_SUFFIX}")
            }

    @staticmethod
    def _fake_scoring(payloads, profil=None):
        """Note tout à 9, et facture un appel de scoring comme le vrai le ferait.

        Le noteur est simulé : sa comptabilité l'est donc aussi, à l'identique de ce
        qu'un `LLMProvider` enregistre — un appel par lot d'articles.
        """
        runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
        return [
            {"id": item["id"], "score": 9, "thematique": "cyber", "angle": "angle"}
            for item in payloads
        ]

    @staticmethod
    def _fake_summary(category, articles, notes=None):
        """Un seul appel de digest pour toute la catégorie, comme le vrai résumeur."""
        runlog.record_chat("digest", "gpt-4o-mini", USAGE)
        return "résumé"

    def test_one_journal_is_written_per_category_with_articles(self):
        journaux = self._run({"Tech": [make_article("a")], "News": [make_article("b")]})

        self.assertEqual({"tech.log.json", "news.log.json"}, set(journaux))

    def test_the_journal_carries_the_articles_their_scores_and_the_costs(self):
        journaux = self._run({"Tech": [make_article("a"), make_article("b")]})

        tech = journaux["tech.log.json"]
        self.assertEqual("audio", tech["resultat"]["statut"])
        self.assertEqual(2, tech["resultat"]["articles"])
        self.assertEqual([9, 9], [entree["score"] for entree in tech["articles"]])
        self.assertEqual(1, tech["couts"]["par_typologie"]["scoring"]["appels"])
        self.assertEqual(1, tech["couts"]["par_typologie"]["tts"]["appels"])
        self.assertGreater(tech["couts"]["total"], 0)

    def test_a_category_costs_one_call_per_poste_up_to_the_scoring_batch(self):
        """Un appel de scoring par lot de 40, un seul résumé, une seule synthèse.

        Ce n'est pas une remontée partielle : le scoring part par lots, et le digest
        comme l'audio sont produits en un appel pour toute la catégorie.
        """
        journaux = self._run({"Tech": [make_article(f"a{rang}") for rang in range(19)]})

        couts = journaux["tech.log.json"]["couts"]["par_typologie"]
        self.assertEqual(1, couts["scoring"]["appels"])
        self.assertEqual(1, couts["resume"]["appels"])
        self.assertEqual(1, couts["tts"]["appels"])

    def test_an_empty_category_gets_no_journal(self):
        """Rien lu, rien noté, rien dépensé : le journal ne dirait que des zéros."""
        journaux = self._run({"Tech": [make_article("a")], "News": []})

        self.assertEqual({"tech.log.json"}, set(journaux))

    def test_the_journal_holds_no_console_transcript(self):
        """Tout ce que la console dit est déjà dans les autres blocs."""
        journaux = self._run({"Tech": [make_article("a")]})

        self.assertNotIn("console", journaux["tech.log.json"])

    def test_a_category_without_selection_gets_its_scores_and_its_cost(self):
        """Rien retenu ne veut pas dire rien dépensé : le scoring, lui, a été payé."""
        journaux = self._run({"Tech": [make_article("a")]}, score_threshold=10)

        tech = journaux["tech.log.json"]
        self.assertEqual("aucun-article-retenu", tech["resultat"]["statut"])
        self.assertEqual(1, tech["couts"]["par_typologie"]["scoring"]["appels"])
        self.assertEqual(0, tech["couts"]["par_typologie"]["tts"]["appels"])
        self.assertEqual(9, tech["articles"][0]["score"])
        self.assertFalse(tech["articles"][0]["retenu"])

    def test_the_journal_records_the_settings_that_explain_it(self):
        journaux = self._run({"Tech": [make_article("a")]})

        parametres = journaux["tech.log.json"]["parametres"]
        self.assertEqual(7, parametres["seuil"])
        # La règle entière, et non le seul seuil : deux catégories du même jour n'ont
        # plus forcément le même, et le repli change ce qui est retenu.
        self.assertEqual(5, parametres["seuil_repli"])
        self.assertEqual(12, parametres["plafond"])
        self.assertIn("minimum_retenus", parametres)
        # Qui fait quoi : le journal fixe le fournisseur et le modèle de chaque action.
        self.assertEqual(
            set(("scoring", "article", "digest", "ephemeride", "tts")),
            set(parametres["fournisseurs"]),
        )
        self.assertTrue(parametres["fournisseurs"]["digest"]["modele"])
        self.assertTrue(parametres["fournisseurs"]["tts"]["voix"])
        self.assertTrue(parametres["empreinte_scoring"])


    def test_the_journal_records_the_threshold_actually_applied(self):
        """Sans lui, un journal replié ne dit pas pourquoi des articles à cinq sont retenus."""
        articles = [make_article(f"a{rang}") for rang in range(3)]

        journaux = self._run({"Tech": articles}, min_digest_items=5, fallback_threshold=5)

        resultat = journaux["tech.log.json"]["resultat"]
        self.assertEqual(5, resultat["seuil_applique"])
        self.assertEqual(7, journaux["tech.log.json"]["parametres"]["seuil"])


if __name__ == "__main__":
    unittest.main()
