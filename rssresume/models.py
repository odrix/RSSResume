"""Objets métier échangés entre les modules."""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib

#: Thématiques produites par le scoring, dans leur ordre de lecture naturel.
THEMATIQUES = ("reglementaire", "cyber", "marche", "stack", "autre")
DEFAULT_THEMATIQUE = "autre"


@dataclasses.dataclass(frozen=True)
class Note:
    """Ce que le scoring a produit pour un article, en entier.

    Le score seul pilotait la sélection et le reste était jeté. `thematique` sert
    maintenant à regrouper les sujets dans l'audio, et `angle` — la phrase qui dit
    en quoi l'article compte pour ce profil — est passé au résumeur : c'est
    exactement le contexte qui lui manquait, et il est déjà payé.

    `angle` n'est pas persisté dans FreshRSS : une phrase entière n'est pas un tag.
    Un score relu du cache revient donc avec un angle vide, ce dont le prompt tient
    compte. Le score et la thématique, eux, sont mis en tag et survivent.
    """

    score: int
    thematique: str = DEFAULT_THEMATIQUE
    angle: str = ""


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
class Link:
    """Un article retenu et son lien, tel qu'il figure dans le corps de l'email."""

    title: str
    source: str
    url: str


@dataclasses.dataclass(frozen=True)
class CategoryDigest:
    category: str
    articles: list[Article]
    summary_text: str
    #: Articles retenus par le scoring pour entrer dans le résumé.
    selected: list[Article] = dataclasses.field(default_factory=list)
    #: Notes calculées lors de cette exécution, à écrire dans FreshRSS. {item_id: Note}
    new_notes: dict[str, Note] = dataclasses.field(default_factory=dict)
    #: Articles notés avec un ancien prompt : leurs tags sont à nettoyer avant renotation.
    stale_item_ids: list[str] = dataclasses.field(default_factory=list)
    #: Fichier audio produit, ou None si la catégorie n'avait aucun article.
    audio_path: pathlib.Path | None = None
    #: Marqueur `.no-article` écrit à la place de l'audio pour une catégorie vide.
    marker_path: pathlib.Path | None = None

    @property
    def links(self) -> list[Link]:
        """Articles retenus et leurs URL, dans l'ordre de lecture du résumé.

        Dérivé de `selected`, pas stocké : deux listes à tenir à jour finiraient par
        diverger. Le résumé, lui, ne cite aucune URL — le modèle les inventerait — mais
        l'email doit rester cliquable, et ces liens en sont le seul moyen.
        """
        return [
            Link(title=article.title, source=article.feed_title, url=article.url)
            for article in self.selected
            if article.url
        ]
