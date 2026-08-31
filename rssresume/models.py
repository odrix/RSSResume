"""Objets métier échangés entre les modules."""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
from typing import Callable, Iterable

#: Fourchette des articles « à surveiller » : notés assez haut pour mériter un lien dans
#: l'email, trop bas pour entrer dans le résumé raconté. En dessous de 4, l'article n'a
#: rien à faire dans la journée ; à 7, il est retenu — et entre les deux se trouvent
#: exactement ceux dont on veut le titre sans vouloir en entendre parler.
WATCHLIST_MIN = 4
WATCHLIST_MAX = 6

#: Thématiques produites par le scoring, dans leur ordre de lecture naturel.
THEMATIQUES = ("reglementaire", "cyber", "marche", "stack", "autre")
DEFAULT_THEMATIQUE = "autre"


@dataclasses.dataclass(frozen=True)
class SelectionRule:
    """Qui entre dans le digest d'une catégorie : le seuil, son repli, et le plafond.

    Un seuil unique ne suffisait à aucune des deux extrémités. Dans une catégorie
    généraliste, tout est « intéressant à connaître » sans être actionnable : à 7, elle
    se vidait tous les jours. Et n'importe quelle catégorie, un jour creux, rendait un
    digest d'un seul sujet là où descendre d'un cran en donnait cinq.

    D'où deux réglages de plus, tous deux réglables par catégorie, et une règle qui se
    lit d'un bloc au lieu d'être étalée dans la sélection : le seuil normal, le seuil de
    repli, le nombre d'articles en dessous duquel le repli s'applique, et le plafond.
    """

    seuil: int
    #: Seuil de secours, appliqué à la journée entière — et non aux seuls articles
    #: manquants — quand le seuil normal ne retient pas `minimum` articles. Égal au
    #: seuil, ou supérieur, il ne fait jamais rien.
    seuil_repli: int
    #: Nombre de retenus en dessous duquel le repli s'applique. `0` le désactive.
    minimum: int
    plafond: int

    def seuil_du_jour(self, scores: Iterable[int]) -> int:
        """Le seuil réellement appliqué, une fois connus les scores de la journée.

        Le repli abaisse le seuil pour tout le monde : c'est ce qui le distingue d'un
        remplissage jusqu'à `minimum`. Une journée peut donc rendre plus de `minimum`
        articles — seul le plafond la borne.
        """
        atteints = sum(1 for score in scores if score >= self.seuil)
        if atteints >= self.minimum:
            return self.seuil
        return min(self.seuil, self.seuil_repli)

    def appliquer[T](self, articles: Iterable[T], score: Callable[[T], int]) -> "Selection[T]":
        """Applique la règle à une journée : ce qu'elle retient, et à quel seuil.

        Le seuil appliqué repart avec la sélection plutôt que d'être recalculé par
        l'appelant : c'est lui qui explique le marqueur d'une catégorie vide et la ligne
        du journal, et deux calculs séparés finiraient un jour par ne plus dire pareil.

        Le plafond s'applique sur le score seul : c'est lui qui décide qui entre dans le
        digest, la thématique ne décide que de l'ordre dans lequel on les raconte.
        """
        classes = sorted(articles, key=score, reverse=True)
        seuil = self.seuil_du_jour(score(article) for article in classes)
        retenus = [article for article in classes if score(article) >= seuil]
        return Selection(retenus=retenus[: self.plafond], seuil=seuil, regle=self)


@dataclasses.dataclass(frozen=True)
class Selection[T]:
    """Ce qu'une `SelectionRule` a retenu d'une journée, et à quel seuil elle l'a fait."""

    retenus: list[T]
    #: Le seuil réellement appliqué : celui de la catégorie, ou son repli.
    seuil: int
    regle: SelectionRule

    @property
    def repliee(self) -> bool:
        """Vrai quand le seuil de repli a été appliqué faute d'assez d'articles."""
        return self.seuil < self.regle.seuil


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
class Ephemeride:
    """Ce qui ouvre l'email : un jour, sa fête, et un fait survenu à cette date.

    `jour` est celui de l'ENVOI, jamais celui que le digest raconte. Les deux diffèrent
    tous les matins : le passage de 7 h résume la veille (`RSSRESUME_SCHEDULE_DAYS_BACK`),
    et une lettre qui s'ouvrirait sur la date d'hier daterait d'un jour dans la boîte de
    son lecteur. Le titre, lui, garde la date du contenu — c'est ce qu'il nomme.

    Il est porté ici plutôt que déduit à l'affichage parce que `fete` et `texte` en
    dépendent tous les deux : les trois doivent parler de la même date, et un seul
    champ garantit qu'ils ne se désynchronisent pas.

    `origine` n'est pas décoratif : une éphéméride écrite par le modèle et une ligne
    tirée de la table embarquée ne se relisent pas avec la même confiance, et le
    journal de la journée doit dire laquelle a servi.

    Ici et non dans `ephemeride.py` : `runlog` la relit pour renvoyer une journée
    passée, et `ephemeride.py` appelle un fournisseur qui importe déjà `runlog`.
    """

    #: Le jour de l'envoi, celui dont la lettre s'ouvre.
    jour: dt.date
    #: « sainte Monique », « la Toussaint ». Vide si la table n'a rien pour cette date.
    fete: str = ""
    #: Le fait historique, vide quand aucune des sources n'en a.
    texte: str = ""
    #: `llm`, `table` ou `calendrier`, du plus au moins renseigné.
    origine: str = "calendrier"


#: Le texte du montage vient du modèle, qui a enchaîné les résumés de catégorie.
ORIGINE_MONTAGE = "montage"
#: Il vient de l'assemblage local : les résumés mis bout à bout, sans transitions ni
#: conclusion. Aucun fournisseur, ou un appel qui a échoué.
ORIGINE_ASSEMBLAGE = "assemblage"


@dataclasses.dataclass(frozen=True)
class Montage:
    """L'audio unique d'une journée : le texte qui a été dit, et le fichier produit.

    Le pendant de `Ephemeride` pour le mode `global` : un objet de valeur que le journal
    de la journée écrit et que `--send-only` relit, sans rien rappeler à personne.

    `origine` n'est pas décoratif, pour la même raison qu'ailleurs : un montage écrit par
    le modèle et des résumés mis bout à bout ne s'écoutent pas pareil, et un audio
    dégradé ne doit pas passer pour un audio réussi. C'est le journal qui le dit, faute
    de quoi il faudrait réécouter pour s'en apercevoir.

    Le texte est gardé parce qu'il est ce que la voix a lu : c'est le seul endroit où
    juger une transition sans relancer le fichier, et ce que `--send-only` renvoie.
    """

    texte: str = ""
    audio_path: pathlib.Path | None = None
    origine: str = ORIGINE_MONTAGE


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
    #: Articles notés entre `WATCHLIST_MIN` et `WATCHLIST_MAX` et non retenus. Ils sont
    #: déjà lus et déjà notés : les taire revenait à jeter la moitié de ce que la
    #: journée a coûté, alors qu'un titre et un lien suffisent à les rendre utiles.
    watchlist: list[Article] = dataclasses.field(default_factory=list)

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

    @property
    def watchlist_links(self) -> list[Link]:
        """Les articles à surveiller et leurs URL, les mieux notés en tête.

        Même dérivation que `links`, sur l'autre bout de la sélection : ce que le
        résumé n'a pas raconté mais qui vaut un coup d'œil.
        """
        return [
            Link(title=article.title, source=article.feed_title, url=article.url)
            for article in self.watchlist
            if article.url
        ]
