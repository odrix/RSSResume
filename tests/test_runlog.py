"""Journal d'exécution : contenu du `.log.json` et rattachement des appels à la catégorie."""

import dataclasses
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import certfr, pricing, runlog
from rssresume.audio import AudioGenerator
from rssresume.digest import DigestService
from rssresume.llm.openai import OpenAIProvider
from rssresume.models import Article, Note
from rssresume.llm.providers import Settings, Voice
from tests.support import FakeEmailSender, FakeFreshRSSClient, FakeScorer, make_config

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


class DayAggregationTests(unittest.TestCase):
    """La somme de la journée : ce que le disque ne porte nulle part.

    Chaque catégorie écrit son fichier, la journée écrit le sien, et personne
    n'additionne les uns aux autres. Le cumul est la seule vue qui dise ce que la
    matinée entière a coûté — et il ne doit rien changer aux fichiers écrits.
    """

    @staticmethod
    def _journee(tmpdir):
        """Deux catégories qui facturent, plus l'éphéméride de la journée."""
        racine = pathlib.Path(tmpdir)
        with runlog.day_scope(DAY, racine) as jour:
            with runlog.category_scope("Tech", "tech", DAY, racine):
                runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
                runlog.record_chat("digest", "gpt-4o-mini", USAGE)
            with runlog.category_scope("News", "news", DAY, racine):
                runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
                runlog.record_tts("tts-1", "alloy", "a" * 1000)
            runlog.record_chat("ephemeride", "gpt-4o-mini", USAGE)
        return jour

    def test_the_day_sums_what_every_category_spent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            couts = self._journee(tmpdir).cumul().as_json()

            postes = couts["par_typologie"]
            self.assertEqual(2, postes["scoring"]["appels"])
            self.assertEqual(1, postes["resume"]["appels"])
            self.assertEqual(1, postes["ephemeride"]["appels"])
            self.assertEqual(1, postes["tts"]["appels"])
            # Quatre complétions à 1000 tokens d'entrée, la synthèse n'en facturant aucun.
            self.assertEqual(4000, sum(poste["tokens_entree"] for poste in postes.values()))
            self.assertEqual(2000, sum(poste["tokens_sortie"] for poste in postes.values()))

    def test_the_total_is_the_sum_of_the_three_journals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jour = self._journee(tmpdir)

            categories = [enfant.cumul().as_json()["total"] for enfant in jour.enfants]
            propre = runlog.Comptes(jour.calls).as_json()["total"]

            self.assertAlmostEqual(sum(categories) + propre, jour.cumul().as_json()["total"], places=6)

    def test_the_written_files_still_bill_only_what_each_journal_spent(self):
        """Le cumul vit en mémoire : `journee.json` ne doit pas hériter des catégories.

        Sans quoi additionner les fichiers d'une journée — ce que fait n'importe qui
        devant un répertoire de sortie — compterait deux fois chaque catégorie.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            jour = self._journee(tmpdir)

            ecrits = {
                nom: json.loads((racine / nom).read_text(encoding="utf-8"))["couts"]
                for nom in (runlog.DAY_LOG_NAME, "tech.log.json", "news.log.json")
            }
            self.assertEqual(1, len(ecrits[runlog.DAY_LOG_NAME]["appels"]))
            self.assertEqual(2, len(ecrits["tech.log.json"]["appels"]))
            self.assertEqual(2, len(ecrits["news.log.json"]["appels"]))
            # Le bloc écrit est exactement celui des appels propres du journal.
            self.assertEqual(runlog.Comptes(jour.calls).as_json(), ecrits[runlog.DAY_LOG_NAME])
            self.assertEqual(5, len(jour.cumul().as_json()["appels"]))

    def test_a_category_that_failed_still_counts_in_the_day(self):
        """Elle a dépensé sans rien rendre : c'est exactement ce qu'on veut voir compté."""
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(DAY, racine) as jour:
                with self.assertRaises(RuntimeError):
                    with runlog.category_scope("Tech", "tech", DAY, racine):
                        runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
                        raise RuntimeError("le fournisseur a lâché")

            self.assertEqual(1, jour.cumul().as_json()["par_typologie"]["scoring"]["appels"])


class RecapitulatifTests(unittest.TestCase):
    """Le texte de fin d'exécution : ce qu'on lit dans la console après le digest."""

    @staticmethod
    def _texte(remplir):
        with tempfile.TemporaryDirectory() as tmpdir:
            racine = pathlib.Path(tmpdir)
            with runlog.day_scope(DAY, racine) as jour:
                remplir(racine)
            return jour.recapitulatif()

    def test_every_billing_typologie_gets_its_line_and_the_day_its_total(self):
        def remplir(racine):
            with runlog.category_scope("Tech", "tech", DAY, racine):
                runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
                runlog.record_chat("digest", "gpt-4o-mini", USAGE)
                runlog.record_tts("tts-1", "alloy", "a" * 1000)
            runlog.record_chat("ephemeride", "gpt-4o-mini", USAGE)

        texte = self._texte(remplir)

        self.assertIn("scoring : 1 appel(s), 1000 token(s) en entrée, 500 en sortie", texte)
        self.assertIn("résumé : 1 appel(s)", texte)
        self.assertIn("éphéméride : 1 appel(s)", texte)
        # La synthèse est facturée à la longueur du texte : sans les caractères, sa
        # ligne n'afficherait que des zéros là où elle coûte le plus.
        self.assertIn(
            "synthèse vocale : 1 appel(s), 0 token(s) en entrée, 0 en sortie, "
            "1000 caractère(s) de synthèse",
            texte,
        )
        self.assertIn("total : 4 appel(s), 3000 token(s) en entrée, 1500 en sortie", texte)
        self.assertIn("USD", texte)

    def test_a_typologie_without_any_call_is_left_out(self):
        """Trois lignes à zéro noieraient la seule qui porte quelque chose."""
        texte = self._texte(lambda racine: runlog.record_chat("ephemeride", "gpt-4o-mini", USAGE))

        self.assertIn("éphéméride :", texte)
        self.assertNotIn("synthèse vocale", texte)
        self.assertNotIn("scoring", texte)

    def test_the_currency_is_the_one_the_journal_carries(self):
        texte = self._texte(lambda racine: runlog.record_chat("ephemeride", "gpt-4o-mini", USAGE))

        self.assertIn(f"0.000450 {pricing.CURRENCY}", texte)

    def test_an_untarifed_model_voids_the_total_and_says_why(self):
        """Un total muet est pire que pas de total : celui qui le lit le reporte."""

        def remplir(racine):
            with runlog.category_scope("Tech", "tech", DAY, racine):
                runlog.record_chat("scoring", "gpt-4o-mini", USAGE)
                runlog.record_chat("digest", "modele-maison", USAGE)

        texte = self._texte(remplir)

        self.assertIn("coût inconnu", texte)
        self.assertIn("modele-maison", texte)
        self.assertIn("RSSRESUME_PRICES", texte)
        self.assertNotIn("USD", texte)

    def test_a_token_billed_tts_makes_the_total_approximate(self):
        """La synthèse ne rend aucun compteur : son coût est déduit du texte envoyé."""
        texte = self._texte(
            lambda racine: runlog.record_tts("gpt-4o-mini-tts", "alloy", "a" * 1000)
        )

        self.assertIn("environ", texte)

    def test_a_day_without_any_call_says_so_rather_than_showing_a_zero(self):
        """Tout relu du cache, ou `--dry-run` : un « 0.000000 USD » laisserait croire à une mesure."""
        texte = self._texte(lambda racine: None)

        self.assertEqual("Consommation IA : aucun appel au fournisseur", texte)
        self.assertNotIn("total", texte)


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
            set(("scoring", "article", "digest", "ephemeride", "montage", "tts")),
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


class CertfrJournalTests(unittest.TestCase):
    """Le journal d'une catégorie déterministe : rien de facturé, et rien de menteur.

    Le journal sert à deux choses ici, et aucune n'est le coût : dire contre quelle
    liste de composants la journée a été appariée, et rester relisible par
    `--send-only`. C'est ce dernier point qui impose la forme — `retenu`, `rang_digest`,
    et un `score` à `null` pour qu'aucun avis n'entre par erreur dans la liste de veille.
    """

    CATEGORIE = "1 - Alertes et avis CERT-FR ANSSI"
    SLUG = "1-alertes-et-avis-cert-fr-anssi.log.json"

    def _avis(self, titre, contenu="", item_id="avis-1"):
        return Article(
            item_id=item_id,
            category=self.CATEGORIE,
            title=titre,
            url=f"https://www.cert.ssi.gouv.fr/avis/{item_id}/",
            published_at=dt.datetime(2026, 8, 26, 6, 0, tzinfo=dt.timezone.utc),
            feed_title="CERT-FR - Avis de securite",
            content_text=contenu,
        )

    def _run(self, articles):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = dataclasses.replace(
                make_config(tmpdir),
                categories=[self.CATEGORIE],
                certfr_categories=[self.CATEGORIE],
            )
            DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({self.CATEGORIE: articles}),
                scorer=FakeScorer(),
                summary_generator=mock.Mock(),
                audio_generator=mock.Mock(),
                email_sender=FakeEmailSender(),
                certfr_service=certfr.CertfrService(
                    certfr.Stack([certfr.Composant("Keycloak", ["RH-SSO"])])
                ),
            ).run(DAY, send_email=False, write_tags=False, mark_read=False)
            chemin = pathlib.Path(tmpdir) / DAY.isoformat() / self.SLUG
            return json.loads(chemin.read_text(encoding="utf-8"))

    def test_a_deterministic_category_bills_nothing(self):
        """Zéro appel et zéro dollar : c'est le signal recherché, pas un journal amputé."""
        journal = self._run([self._avis("Multiples vulnérabilités dans Keycloak")])

        self.assertEqual(0.0, journal["couts"]["total"])
        self.assertEqual([], journal["couts"]["appels"])
        self.assertTrue(journal["couts"]["tarification_complete"])

    def test_the_settings_describe_the_stack_instead_of_a_threshold(self):
        """Un seuil et une empreinte de prompt n'ont aucun sens sans scoring."""
        journal = self._run([self._avis("Multiples vulnérabilités dans Keycloak")])

        parametres = journal["parametres"]
        self.assertEqual(runlog.TRAITEMENT_DETERMINISTE, parametres["traitement"])
        self.assertEqual(1, parametres["composants"])
        self.assertTrue(parametres["empreinte_stack"])
        self.assertNotIn("seuil", parametres)
        self.assertNotIn("empreinte_scoring", parametres)

    def test_the_status_says_the_category_was_not_judged(self):
        """Sans statut à part, une journée sans appariement se lirait comme un seuil trop haut."""
        journal = self._run([self._avis("Multiples vulnérabilités dans Google Chrome")])

        self.assertEqual("deterministe", journal["resultat"]["statut"])
        self.assertEqual(1, journal["resultat"]["articles"])
        self.assertEqual(0, journal["resultat"]["retenus"])
        self.assertIsNone(journal["resultat"]["audio"])

    def test_the_matched_advisories_carry_what_the_replay_needs(self):
        journal = self._run(
            [
                self._avis("Multiples vulnérabilités dans Google Chrome"),
                self._avis("Multiples vulnérabilités dans RH-SSO", item_id="avis-2"),
            ]
        )

        apparie = next(e for e in journal["articles"] if e["item_id"] == "avis-2")
        ecarte = next(e for e in journal["articles"] if e["item_id"] == "avis-1")
        self.assertTrue(apparie["retenu"])
        self.assertEqual(1, apparie["rang_digest"])
        self.assertFalse(ecarte["retenu"])
        # Le score reste nul : `_a_surveiller` exige un entier dans la fourchette 4-6,
        # donc aucun avis ne peut entrer par accident dans la liste de veille.
        self.assertIsNone(apparie["score"])
        self.assertIsNone(ecarte["score"])

    def test_the_journal_carries_the_sentence_the_email_shows(self):
        journal = self._run([self._avis("Multiples vulnérabilités dans Keycloak")])

        self.assertIn("touche la stack : Keycloak", journal["resume"])


if __name__ == "__main__":
    unittest.main()
