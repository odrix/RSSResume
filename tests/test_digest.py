import dataclasses
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import certfr
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.models import ORIGINE_MONTAGE, Article, CategoryDigest, Link, Montage
from rssresume.summaries import SummaryGenerator
from tests.support import FakeAudioGenerator, FakeEmailSender, FakeFreshRSSClient, make_config

DAY = dt.date(2026, 8, 23)


def make_article(category="Tech", title="Nouveau modèle", item_id="item-1"):
    return Article(
        item_id=item_id,
        category=category,
        title=title,
        url="https://example.com/article",
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="AI Feed",
        content_text="Un nouveau modèle améliore les performances.",
    )


class MarkAsReadTests(unittest.TestCase):
    def _run(self, articles_by_category, **kwargs):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            client = FakeFreshRSSClient(articles_by_category)
            service = DigestService(
                config=config,
                freshrss_client=client,
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )
            service.run(DAY, **kwargs)
            return client

    def test_processed_articles_are_marked_as_read(self):
        articles = [make_article(item_id="item-1"), make_article(item_id="item-2")]
        client = self._run({"Tech": articles, "News": []}, send_email=False)

        self.assertEqual(["item-1", "item-2"], [article.item_id for article in client.marked_as_read])

    def test_dry_run_does_not_mark_articles_as_read(self):
        client = self._run({"Tech": [make_article()], "News": []}, send_email=False, write_tags=False, mark_read=False)

        self.assertEqual([], client.marked_as_read)

    def test_empty_categories_trigger_no_marking(self):
        client = self._run({"Tech": [], "News": []}, send_email=False)

        self.assertEqual([], client.marked_as_read)

    def test_digested_articles_are_tagged(self):
        articles = [make_article(item_id="item-1"), make_article(item_id="item-2")]
        client = self._run({"Tech": articles, "News": []}, send_email=False)

        self.assertEqual(["item-1", "item-2"], client.digested)

    def test_dry_run_does_not_tag_digested_articles(self):
        client = self._run({"Tech": [make_article()], "News": []}, send_email=False, write_tags=False, mark_read=False)

        self.assertEqual([], client.digested)

    def test_empty_categories_are_not_tagged(self):
        client = self._run({"Tech": [], "News": []}, send_email=False)

        self.assertEqual([], client.digested)


class DigestServiceTests(unittest.TestCase):
    def test_run_generates_one_audio_per_non_empty_category_and_sends_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article()], "News": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(DAY)

            self.assertEqual(["Tech", "News"], [digest.category for digest in digests])
            self.assertIn("Nouveau modèle", digests[0].summary_text)
            self.assertIn("Aucun nouvel article", digests[1].summary_text)
            self.assertEqual(1, len(email_sender.messages))
            self.assertEqual([pathlib.Path(tmpdir) / "2026-08-23" / "tech.wav"], email_sender.messages[0][2])

    def test_email_body_carries_the_links_the_audio_cannot(self):
        """L'audio ne cite aucune URL ; l'email est le seul endroit pour retrouver l'article."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            email_sender = FakeEmailSender()
            DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article()], "News": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            ).run(DAY)

            subject, body, _, html = email_sender.messages[0]

            self.assertIn("À lire :", body)
            self.assertIn("Nouveau modèle (AI Feed)", body)
            self.assertIn("https://example.com/article", body)
            # La catégorie sans article n'ajoute pas de bloc de liens vide.
            self.assertEqual(1, body.count("À lire :"))
            # Le même lien est cliquable dans la version mise en page.
            self.assertIn('href="https://example.com/article"', html)
            self.assertIn("Veille du 23 août 2026", subject)

    def test_run_writes_one_directory_per_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [make_article()], "News": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            day_dir = pathlib.Path(tmpdir) / "2026-08-23"
            self.assertEqual(day_dir, digests[0].audio_path.parent)
            self.assertEqual(day_dir, digests[1].marker_path.parent)

    def test_run_writes_empty_marker_instead_of_audio_for_empty_category(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [], "News": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            marker = digests[0].marker_path
            self.assertIsNone(digests[0].audio_path)
            self.assertEqual(pathlib.Path(tmpdir) / "2026-08-23" / "tech.no-article", marker)
            self.assertTrue(marker.exists())
            self.assertEqual(0, marker.stat().st_size)

    def test_run_never_calls_generators_for_empty_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_generator = mock.Mock()
            audio_generator = mock.Mock()
            service = DigestService(
                config=make_config(tmpdir),
                freshrss_client=FakeFreshRSSClient({"Tech": [], "News": []}),
                summary_generator=summary_generator,
                audio_generator=audio_generator,
                email_sender=FakeEmailSender(),
            )

            service.run(DAY, send_email=False)

            summary_generator.summarize.assert_not_called()
            audio_generator.synthesize.assert_not_called()

    def test_run_uses_discovered_categories_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "categories": []})
            email_sender = FakeEmailSender()
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Culture": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=email_sender,
            )

            digests = service.run(DAY, send_email=False)

            self.assertEqual(["Culture"], [digest.category for digest in digests])
            self.assertEqual([], email_sender.messages)

    def test_run_skips_excluded_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
            config = AppConfig(**{**config.__dict__, "categories": [], "excluded_categories": ["non classé"]})
            service = DigestService(
                config=config,
                freshrss_client=FakeFreshRSSClient({"Tech": [], "Non classé": []}),
                summary_generator=SummaryGenerator(None),
                audio_generator=FakeAudioGenerator(),
                email_sender=FakeEmailSender(),
            )

            digests = service.run(DAY, send_email=False)

            self.assertEqual(["Tech"], [digest.category for digest in digests])


class LinksTests(unittest.TestCase):
    """`CategoryDigest.links` est dérivé de la sélection, jamais saisi à part."""

    def test_links_follow_the_reading_order_of_the_summary(self):
        selected = [
            make_article(title="Premier", item_id="item-1"),
            make_article(title="Second", item_id="item-2"),
        ]
        digest = CategoryDigest(
            category="Tech", articles=selected, summary_text="résumé", selected=selected
        )

        self.assertEqual(
            [
                Link("Premier", "AI Feed", "https://example.com/article"),
                Link("Second", "AI Feed", "https://example.com/article"),
            ],
            digest.links,
        )

    def test_an_article_without_url_yields_no_link(self):
        selected = [dataclasses.replace(make_article(), url="")]
        digest = CategoryDigest(
            category="Tech", articles=selected, summary_text="résumé", selected=selected
        )

        self.assertEqual([], digest.links)

    def test_a_category_without_selection_has_no_link(self):
        digest = CategoryDigest(category="Tech", articles=[], summary_text="aucun article")

        self.assertEqual([], digest.links)


class CertfrRoutingTests(unittest.TestCase):
    """Une catégorie routée quitte le pipeline LLM en entier, et rien ne l'y ramène.

    C'est toute la promesse du traitement déterministe : volume élevé, format
    répétitif, mauvais rendu audio. Un scoring, un résumé ou une synthèse qui
    repasserait par là annulerait l'économie sans que rien ne le dise, sinon la facture.
    """

    CATEGORIE = "1 - Alertes et avis CERT-FR ANSSI"

    def _avis(self, titre, contenu="", item_id="avis-1"):
        return dataclasses.replace(
            make_article(category=self.CATEGORIE, title=titre, item_id=item_id),
            content_text=contenu,
            url=f"https://www.cert.ssi.gouv.fr/avis/{item_id}/",
            feed_title="CERT-FR - Avis de securite",
        )

    def _service(self, tmpdir, articles, routees=None, **collaborateurs):
        config = make_config(tmpdir)
        config = AppConfig(
            **{
                **config.__dict__,
                "categories": [self.CATEGORIE],
                "certfr_categories": [self.CATEGORIE if routees is None else routees],
            }
        )
        client = FakeFreshRSSClient({self.CATEGORIE: articles})
        service = DigestService(
            config=config,
            freshrss_client=client,
            summary_generator=collaborateurs.get("summary_generator") or SummaryGenerator(None),
            audio_generator=collaborateurs.get("audio_generator") or FakeAudioGenerator(),
            email_sender=FakeEmailSender(),
            scorer=collaborateurs.get("scorer"),
            certfr_service=certfr.CertfrService(
                certfr.Stack([certfr.Composant("Keycloak", ["RH-SSO"])])
            ),
        )
        return service, client

    def test_a_routed_category_never_calls_the_scorer_the_summarizer_or_the_tts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scorer, summary_generator, audio_generator = mock.Mock(), mock.Mock(), mock.Mock()
            service, _ = self._service(
                tmpdir,
                [self._avis("Multiples vulnérabilités dans Keycloak (25 août 2026)")],
                scorer=scorer,
                summary_generator=summary_generator,
                audio_generator=audio_generator,
            )

            digest, = service.run(DAY, send_email=False)

            scorer.score_articles.assert_not_called()
            summary_generator.summarize.assert_not_called()
            audio_generator.synthesize.assert_not_called()
            self.assertIsNone(digest.audio_path)

    def test_every_advisory_of_a_routed_category_is_marked_as_read(self):
        """« Les autres avis sont marqués lus sans être résumés » : ils sont tous dans `articles`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service, client = self._service(
                tmpdir,
                [
                    self._avis("Multiples vulnérabilités dans Keycloak (25 août 2026)"),
                    self._avis(
                        "Multiples vulnérabilités dans Google Chrome (26 août 2026)",
                        item_id="avis-2",
                    ),
                ],
            )

            service.run(DAY, send_email=False)

            self.assertEqual(
                ["avis-1", "avis-2"], [article.item_id for article in client.marked_as_read]
            )

    def test_only_the_advisories_touching_the_stack_reach_the_email_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _ = self._service(
                tmpdir,
                [
                    self._avis("Multiples vulnérabilités dans Google Chrome (26 août 2026)"),
                    self._avis(
                        "Multiples vulnérabilités dans RH-SSO (25 août 2026)",
                        "Elles permettent une exécution de code arbitraire à distance.",
                        item_id="avis-2",
                    ),
                ],
            )

            digest, = service.run(DAY, send_email=False)

            self.assertEqual(2, len(digest.articles))
            self.assertEqual(["avis-2"], [article.item_id for article in digest.selected])
            self.assertIn("Keycloak — exécution de code arbitraire à distance", digest.summary_text)

    def test_the_category_is_routed_even_when_the_variable_drops_the_accents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _ = self._service(
                tmpdir,
                [self._avis("Multiples vulnérabilités dans Keycloak (25 août 2026)")],
                routees="1 - alertes et avis cert-fr anssi",
                summary_generator=mock.Mock(),
            )

            digest, = service.run(DAY, send_email=False)

            self.assertIn("avis CERT-FR aujourd'hui", digest.summary_text)

    def test_an_unrouted_category_keeps_the_llm_pipeline(self):
        """Le garde-fou symétrique : sans la variable, rien ne change pour personne."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_generator = mock.Mock()
            summary_generator.summarize.return_value = "Le résumé."
            service, _ = self._service(
                tmpdir,
                [self._avis("Multiples vulnérabilités dans Keycloak (25 août 2026)")],
                routees="Une autre catégorie",
                summary_generator=summary_generator,
            )

            service.run(DAY, send_email=False)

            summary_generator.summarize.assert_called_once()

    def test_a_routed_category_without_any_advisory_writes_the_usual_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _ = self._service(tmpdir, [], summary_generator=mock.Mock())

            digest, = service.run(DAY, send_email=False)

            self.assertTrue(digest.marker_path.exists())
            self.assertIn("Aucun nouvel article", digest.summary_text)


class AudioGlobalTests(unittest.TestCase):
    """Ce que ces tests protègent : en mode `global`, un seul fichier est écrit — celui
    de la journée — et aucune catégorie n'en produit plus. Les deux modes ne doivent
    jamais coexister dans un même répertoire, sans quoi l'email joindrait les deux."""

    def _run(self, articles_by_category, mode, montage_service=None, **kwargs):
        tmpdir = tempfile.mkdtemp()
        config = dataclasses.replace(make_config(tmpdir), audio_mode=mode)
        sender = FakeEmailSender()
        service = DigestService(
            config=config,
            freshrss_client=FakeFreshRSSClient(articles_by_category),
            summary_generator=SummaryGenerator(None),
            audio_generator=FakeAudioGenerator(),
            email_sender=sender,
            montage_service=montage_service,
        )
        digests = service.run(DAY, **kwargs)
        return pathlib.Path(tmpdir) / DAY.isoformat(), digests, sender

    def test_by_category_each_category_keeps_its_own_file(self):
        jour, digests, _ = self._run(
            {"Tech": [make_article()], "News": [make_article(category="News")]},
            "category",
            send_email=False,
        )

        self.assertEqual(["tech.wav", "news.wav"], [d.audio_path.name for d in digests])
        self.assertFalse((jour / "journee.wav").exists())

    def test_globally_a_single_file_carries_the_whole_day(self):
        jour, digests, _ = self._run(
            {"Tech": [make_article()], "News": [make_article(category="News")]},
            "global",
            send_email=False,
        )

        self.assertEqual([None, None], [d.audio_path for d in digests])
        self.assertTrue((jour / "journee.wav").exists())
        # Aucun fichier de catégorie n'a été écrit à côté.
        self.assertEqual([], sorted(jour.glob("tech.wav")))

    def test_the_summaries_are_still_produced_for_the_email(self):
        """Le montage ne les remplace pas : l'email continue de les montrer."""
        _, digests, _ = self._run(
            {"Tech": [make_article()], "News": []}, "global", send_email=False
        )

        self.assertTrue(digests[0].summary_text.strip())

    def test_the_single_file_is_the_only_attachment(self):
        _, _, sender = self._run(
            {"Tech": [make_article()], "News": [make_article(category="News")]}, "global"
        )

        _, _, attachments, _ = sender.messages[0]
        self.assertEqual(["journee.wav"], [chemin.name for chemin in attachments])

    def test_a_day_with_nothing_to_say_writes_no_file_at_all(self):
        """Une salutation suivie d'un silence serait pire qu'une pièce jointe absente."""
        jour, _, _ = self._run({"Tech": [], "News": []}, "global", send_email=False)

        self.assertFalse((jour / "journee.wav").exists())

    def test_the_montage_sees_every_category_once(self):
        montage = mock.Mock()
        montage.ecrire.return_value = Montage(texte="Bonjour. Voici la journée.")

        self._run(
            {"Tech": [make_article()], "News": [make_article(category="News")]},
            "global",
            montage_service=montage,
            send_email=False,
        )

        montage.ecrire.assert_called_once()
        _, digests = montage.ecrire.call_args.args
        self.assertEqual(["Tech", "News"], [digest.category for digest in digests])

    def test_a_summarized_category_is_not_logged_as_a_failure(self):
        """« sans-audio » dit qu'on attendait un fichier et qu'il manque. Ici il ne
        manque rien : il est dans celui de la journée, et le statut doit le dire."""
        jour, _, _ = self._run(
            {"Tech": [make_article()], "News": []}, "global", send_email=False
        )

        journal = json.loads((jour / "tech.log.json").read_text(encoding="utf-8"))
        self.assertEqual("monte", journal["resultat"]["statut"])
        self.assertIsNone(journal["resultat"]["audio"])
        self.assertEqual("global", journal["parametres"]["audio"])

    def test_by_category_the_status_is_unchanged(self):
        jour, _, _ = self._run(
            {"Tech": [make_article()], "News": []}, "category", send_email=False
        )

        journal = json.loads((jour / "tech.log.json").read_text(encoding="utf-8"))
        self.assertEqual("audio", journal["resultat"]["statut"])
        self.assertEqual("tech.wav", journal["resultat"]["audio"])

    def test_the_day_journal_keeps_the_text_that_was_read_aloud(self):
        montage = mock.Mock()
        montage.ecrire.return_value = Montage(texte="Bonjour Adrien. Voici la journée.")

        jour, _, _ = self._run(
            {"Tech": [make_article()], "News": []},
            "global",
            montage_service=montage,
            send_email=False,
        )

        journal = json.loads((jour / "journee.json").read_text(encoding="utf-8"))
        self.assertEqual("Bonjour Adrien. Voici la journée.", journal["montage"]["texte"])
        self.assertEqual("journee.wav", journal["montage"]["audio"])
        self.assertEqual(ORIGINE_MONTAGE, journal["montage"]["origine"])


if __name__ == "__main__":
    unittest.main()
