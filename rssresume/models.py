"""Objets métier échangés entre les modules."""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib


@dataclasses.dataclass(frozen=True)
class Article:
    #: Identifiant FreshRSS de l'article, requis pour le marquer comme lu.
    item_id: str
    category: str
    title: str
    url: str
    published_at: dt.datetime
    feed_title: str
    content_text: str


@dataclasses.dataclass(frozen=True)
class CategoryDigest:
    category: str
    articles: list[Article]
    summary_text: str
    #: Fichier audio produit, ou None si la catégorie n'avait aucun article.
    audio_path: pathlib.Path | None = None
    #: Marqueur `.no-article` écrit à la place de l'audio pour une catégorie vide.
    marker_path: pathlib.Path | None = None
