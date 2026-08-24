"""Complément des avis de vulnérabilité par la page liée."""

import datetime as dt
import unittest
import urllib.error
from unittest import mock

from rssresume import cve
from rssresume.models import Article


def make_article(title, content, url="https://cert.example/avis"):
    return Article(
        item_id="item-1",
        category="Cyber",
        title=title,
        url=url,
        published_at=dt.datetime(2026, 8, 23, 8, 0, tzinfo=dt.timezone.utc),
        feed_title="CERT-FR",
        content_text=content,
    )


class EnrichTests(unittest.TestCase):
    def test_thin_cve_article_gets_the_page_text(self):
        article = make_article("CVE-2026-1234 : RCE dans X", "Un avis a été publié.")

        with mock.patch.object(cve, "fetch_detail", return_value="Versions 1.0 à 1.4.") as fetch:
            enriched = cve.enrich([article])[0]

        fetch.assert_called_once_with(article.url)
        self.assertIn("Un avis a été publié.", enriched.content_text)
        self.assertIn("Versions 1.0 à 1.4.", enriched.content_text)

    def test_article_without_cve_is_left_alone(self):
        article = make_article("Un fournisseur cloud annonce une nouvelle région", "Court.")

        with mock.patch.object(cve, "fetch_detail") as fetch:
            self.assertEqual([article], cve.enrich([article]))

        fetch.assert_not_called()

    def test_substantial_content_needs_no_page(self):
        """Le flux porte déjà le détail : aller le rechercher ne ferait que payer des tokens."""
        article = make_article("CVE-2026-1234 : RCE dans X", "x" * cve.SUFFICIENT_CONTENT_LENGTH)

        with mock.patch.object(cve, "fetch_detail") as fetch:
            self.assertEqual([article], cve.enrich([article]))

        fetch.assert_not_called()

    def test_article_without_url_is_left_alone(self):
        article = make_article("CVE-2026-1234 : RCE dans X", "Court.", url="")

        with mock.patch.object(cve, "fetch_detail") as fetch:
            self.assertEqual([article], cve.enrich([article]))

        fetch.assert_not_called()

    def test_unreachable_page_is_not_blocking(self):
        article = make_article("CVE-2026-1234 : RCE dans X", "Court.")

        with mock.patch.object(cve.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom")):
            self.assertEqual([article], cve.enrich([article]))


class FetchDetailTests(unittest.TestCase):
    def _serve(self, body: bytes, charset="utf-8"):
        response = mock.MagicMock()
        response.read.return_value = body
        response.headers.get_content_charset.return_value = charset
        response.__enter__.return_value = response
        return mock.patch.object(cve.urllib.request, "urlopen", return_value=response)

    def test_scripts_and_tags_are_stripped(self):
        page = b"<html><body><script>var a=1;</script><p>Correctif disponible.</p></body></html>"

        with self._serve(page):
            self.assertEqual("Correctif disponible.", cve.fetch_detail("https://cert.example/avis"))

    def test_detail_is_capped(self):
        page = b"<p>" + b"a" * (cve.MAX_DETAIL_LENGTH + 500) + b"</p>"

        with self._serve(page):
            self.assertEqual(cve.MAX_DETAIL_LENGTH, len(cve.fetch_detail("https://cert.example/avis")))


if __name__ == "__main__":
    unittest.main()
