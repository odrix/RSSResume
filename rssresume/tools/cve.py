"""Complément des articles de vulnérabilité par le texte de la page liée.

Les flux d'alertes ne publient souvent qu'un titre et deux lignes :
« CVE-2026-1234 : élévation de privilèges dans le composant X ». Résumer cela ne
dit ni ce qui est touché, ni s'il faut agir aujourd'hui — le résumé ne peut que
paraphraser le titre. Le détail est sur la page de l'avis : on va donc la lire,
mais seulement pour les articles qui parlent d'une CVE et dont le flux n'a rien
fourni de substantiel.

Aucun échec n'est bloquant : une page injoignable laisse l'article tel quel.
"""

from __future__ import annotations

import dataclasses
import re
import urllib.error
import urllib.request

from rssresume.models import Article
from rssresume.tools import console
from rssresume.tools.text import strip_html_document

CVE_PATTERN = re.compile(r"CVE[-\s]\d{4}[-\s]\d{4,7}", re.IGNORECASE)

#: Au-delà, le flux porte déjà de quoi résumer : la page n'apporterait rien.
SUFFICIENT_CONTENT_LENGTH = 1200
#: Le détail utile d'un avis tient dans les premiers milliers de caractères ;
#: au-delà on paierait des tokens pour des menus et des pieds de page.
MAX_DETAIL_LENGTH = 6000
#: Plafond de lecture : une page de plus de 1 Mo n'est pas un avis de sécurité.
MAX_PAGE_BYTES = 1_000_000
FETCH_TIMEOUT = 15
#: Certains sites d'éditeurs renvoient 403 à un client sans User-Agent.
USER_AGENT = "Mozilla/5.0 (compatible; RSSResume/1.0)"
DETAIL_HEADER = "Détail lu sur la page de l'avis :"


def mentions_cve(article: Article) -> bool:
    return bool(CVE_PATTERN.search(f"{article.title}\n{article.content_text}"))


def enrich(articles: list[Article]) -> list[Article]:
    """Articles de vulnérabilité complétés par le texte de leur page."""
    return [_enriched(article) if _needs_detail(article) else article for article in articles]


def _needs_detail(article: Article) -> bool:
    return (
        bool(article.url)
        and mentions_cve(article)
        and len(article.content_text) < SUFFICIENT_CONTENT_LENGTH
    )


def _enriched(article: Article) -> Article:
    detail = fetch_detail(article.url)
    if not detail:
        return article
    console.detail(f"CVE : {len(detail)} caractère(s) lus sur la page de « {article.title[:60]} »")
    return dataclasses.replace(
        article,
        content_text=f"{article.content_text}\n\n{DETAIL_HEADER}\n{detail}".strip(),
    )


def fetch_detail(url: str) -> str:
    """Texte lisible de la page, chaîne vide si elle n'est pas récupérable."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Un avis inaccessible ne doit pas faire tomber le digest du jour.
        console.detail(f"CVE : page non lue ({url}) : {exc}")
        return ""
    return strip_html_document(raw.decode(charset, errors="replace"))[:MAX_DETAIL_LENGTH]
