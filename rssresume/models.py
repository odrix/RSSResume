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
    #: Tags utilisateur déjà posés sur l'article dans FreshRSS.
    tags: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CategoryDigest:
    category: str
    articles: list[Article]
    summary_text: str
    #: Articles retenus par le scoring pour entrer dans le résumé.
    selected: list[Article] = dataclasses.field(default_factory=list)
    #: Scores calculés lors de cette exécution, à écrire dans FreshRSS. {item_id: score}
    new_scores: dict[str, int] = dataclasses.field(default_factory=dict)
    #: Articles notés avec un ancien prompt : leurs tags sont à nettoyer avant renotation.
    stale_item_ids: list[str] = dataclasses.field(default_factory=list)
    #: Fichier audio produit, ou None si la catégorie n'avait aucun article.
    audio_path: pathlib.Path | None = None
    #: Marqueur `.no-article` écrit à la place de l'audio pour une catégorie vide.
    marker_path: pathlib.Path | None = None
