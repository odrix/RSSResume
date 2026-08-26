"""Utilitaires de texte partagés par les différents modules."""

from __future__ import annotations

import html
import re


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "category"


def no_article_message(category: str) -> str:
    return f"Aucun nouvel article aujourd'hui dans la catégorie {category}."


def no_selection_message(category: str, threshold: int) -> str:
    return (
        f"Aucun article retenu aujourd'hui dans la catégorie {category} "
        f"(score minimal {threshold})."
    )


def strip_html_document(value: str) -> str:
    """Texte lisible d'une page HTML complète.

    `strip_html` retire les balises mais laisse le contenu des `<script>` et
    `<style>` : sur une page web réelle, cela ramène des kilo-octets de
    JavaScript dans le prompt. Ces blocs partent donc avant les balises.
    """
    without_code = re.sub(
        r"(?is)<(script|style|noscript|template|svg)\b[^>]*>.*?</\1\s*>", " ", value or ""
    )
    return strip_html(without_code)
