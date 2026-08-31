"""Utilitaires de texte partagés par les différents modules."""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

#: Balises dont le corps n'est pas du texte à lire. Les retirer avec leur contenu, et pas
#: seulement leurs chevrons, est ce qui empêche du JavaScript, du CSS ou un fragment
#: masqué d'entrer dans le prompt : `<script>` est le vecteur d'injection le plus direct
#: qu'un flux hostile puisse offrir, et le plus coûteux en tokens quand il ne l'est pas.
NON_TEXT_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})


class _VisibleText(HTMLParser):
    """Le texte visible d'un fragment HTML, blocs non textuels compris.

    Écrit contre une regex `<[^>]+>` : elle retirait bien les balises, mais gardait leur
    corps — le JavaScript d'un `<script>` partait au modèle — et un chevron dans un
    attribut lui faisait couper la balise au mauvais endroit. Le parseur de la
    bibliothèque standard connaît ces deux cas, et les commentaires HTML avec.
    """

    def __init__(self) -> None:
        # `convert_charrefs` décode les entités du texte, y compris sans aucune balise.
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        #: Profondeur d'imbrication dans un bloc non textuel : au-dessus de zéro, on n'écrit
        #: rien. Un compteur et non un booléen, pour les `<svg>` imbriqués.
        self._muted = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        # Une balise sépare deux mots : « a<br>b » se lit « a b », jamais « ab ».
        self._parts.append(" ")
        if tag in NON_TEXT_TAGS:
            self._muted += 1

    def handle_endtag(self, tag: str) -> None:
        self._parts.append(" ")
        if tag in NON_TEXT_TAGS and self._muted:
            self._muted -= 1

    def handle_data(self, data: str) -> None:
        if not self._muted:
            self._parts.append(data)

    def text(self) -> str:
        self.close()
        return "".join(self._parts)


def strip_html(value: str) -> str:
    """Texte lisible d'un fragment de flux comme d'une page HTML complète.

    Ce texte finit dans un prompt : tout ce qui n'est pas destiné à être lu — script,
    style, commentaire, balisage inerte — n'a rien à y faire.
    """
    parser = _VisibleText()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", parser.text()).strip()


#: Fin de phrase : une ponctuation forte suivie d'une espace ou de la fin du texte.
SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")
#: En deçà de cette fraction du plafond, aucune frontière de phrase n'est acceptable :
#: un article sans ponctuation forte rendrait sinon une portion dérisoire de son texte.
MIN_SENTENCE_RATIO = 0.6
#: Marque laissée à la coupe. Le modèle doit voir qu'il lit un extrait : sans elle, il
#: conclut sur une fin de texte qui n'en est pas une.
TRUNCATION_MARK = " […]"


def truncate_sentences(value: str, limit: int) -> str:
    """`value` ramené sous `limit` caractères, coupé à la dernière phrase entière.

    Couper au caractère laisse une phrase en l'air, et une phrase en l'air, un modèle la
    termine tout seul — c'est-à-dire l'invente. On recule donc jusqu'à la dernière
    ponctuation forte, sauf si elle est si tôt qu'il ne resterait presque rien.

    Un `limit` nul ou négatif ne plafonne rien : c'est ainsi que le plafond se désactive.
    """
    texte = value or ""
    if limit <= 0 or len(texte) <= limit:
        return texte
    tete = texte[:limit]
    frontieres = [fin.end() for fin in SENTENCE_END.finditer(tete)]
    coupe = (
        frontieres[-1]
        if frontieres and frontieres[-1] >= limit * MIN_SENTENCE_RATIO
        else limit
    )
    return tete[:coupe].rstrip() + TRUNCATION_MARK


#: Frontière de paragraphe : la coupe passe juste après la ligne vide, qui reste donc
#: attachée au morceau qui précède.
PARAGRAPH_END = re.compile(r"(?<=\n\n)")


def decouper(value: str, limit: int) -> list[str]:
    """`value` en morceaux d'au plus `limit` caractères, coupés là où la voix respire.

    Les endpoints de synthèse plafonnent leur entrée — 4096 caractères chez OpenAI — et
    un texte qui dépasse n'est pas tronqué : il est refusé, ce qui fait perdre la journée.
    Le texte part donc en plusieurs appels, dont les audios sont raboutés.

    Trois frontières, de la moins audible à la plus : entre deux paragraphes, entre deux
    phrases, et seulement en dernier recours entre deux mots. La reprise ne s'entend
    presque pas quand elle tombe là où la voix marquait déjà une pause ; au milieu d'une
    proposition, elle s'entend beaucoup. Un mot plus long que le plafond est coupé dedans :
    à ce stade il n'y a plus de bonne coupe, seulement une mauvaise et une exception.

    Un `limit` nul ou négatif ne découpe rien : c'est ainsi qu'un fournisseur qui ne
    déclare aucun plafond reçoit son texte d'un seul tenant.
    """
    texte = value or ""
    if limit <= 0 or len(texte) <= limit:
        return [texte] if texte else []
    return _emballer(_unites(texte, limit), limit)


def _unites(texte: str, limit: int) -> list[str]:
    """Le texte en pièces qui tiennent toutes sous le plafond, séparateurs compris.

    On ne descend d'un niveau que pour la pièce qui dépasse : un paragraphe qui tient
    reste entier, même si son voisin a dû être coupé phrase à phrase.
    """
    unites: list[str] = []
    for paragraphe in PARAGRAPH_END.split(texte):
        if not paragraphe:
            continue
        if len(paragraphe) <= limit:
            unites.append(paragraphe)
            continue
        for phrase in _phrases(paragraphe):
            if len(phrase) <= limit:
                unites.append(phrase)
            else:
                unites.extend(_mots(phrase, limit))
    return unites


def _phrases(bloc: str) -> list[str]:
    """Le bloc coupé après chaque ponctuation forte, celle-ci restant sur sa phrase."""
    coupes = [fin.end() for fin in SENTENCE_END.finditer(bloc)]
    morceaux = []
    depart = 0
    for coupe in coupes:
        morceaux.append(bloc[depart:coupe])
        depart = coupe
    morceaux.append(bloc[depart:])
    return [morceau for morceau in morceaux if morceau]


def _mots(phrase: str, limit: int) -> list[str]:
    """La phrase trop longue, coupée sur ses espaces, et dans un mot s'il le faut."""
    morceaux = []
    reste = phrase
    while len(reste) > limit:
        coupe = reste.rfind(" ", 0, limit + 1)
        morceaux.append(reste[: coupe if coupe > 0 else limit])
        reste = reste[coupe if coupe > 0 else limit :]
    if reste:
        morceaux.append(reste)
    return morceaux


def _emballer(unites: list[str], limit: int) -> list[str]:
    """Les pièces regroupées au plus large : moins d'appels, donc moins de reprises."""
    morceaux: list[str] = []
    courant = ""
    for unite in unites:
        if courant and len(courant) + len(unite) > limit:
            morceaux.append(courant)
            courant = unite
        else:
            courant += unite
    if courant:
        morceaux.append(courant)
    return [morceau.strip() for morceau in morceaux if morceau.strip()]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "category"


#: Un mot, une fois la casse et les accents retirés : lettres latines et chiffres.
WORD = re.compile(r"[a-z0-9]+")


def casefold_ascii(value: str) -> str:
    """Texte replié pour comparaison : casse repliée ET accents retirés.

    `casefold()` seul ne suffit pas partout. Il replie la casse mais laisse les accents,
    et les libellés de catégorie FreshRSS en portent — « 1 - Alertes et avis CERT-FR
    ANSSI ». Or un libellé recopié dans une variable d'environnement, puis collé dans le
    panneau d'un hébergeur, y perd régulièrement ses accents : `.env.local` porte déjà un
    `RSSRESUME_CATEGORY_THRESHOLDS` écrit sans. La comparaison échouait alors sans rien
    dire, ce qui est exactement le genre de réglage qu'on croit posé pendant des semaines.

    La décomposition NFKD sépare la lettre de base de son diacritique ; ne restent que
    les caractères qui ne se combinent à rien.
    """
    decompose = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()


def words(value: str) -> tuple[str, ...]:
    """Les mots d'un texte, casse et accents retirés, ponctuation jetée.

    Découper avant de comparer est ce qui distingue un appariement d'un `in` : chercher
    « Go » dans « Google Chrome » réussit sur la chaîne et se trompe sur le produit. Sur
    des suites de mots, `Go` ne peut plus se cacher dans `Google`.
    """
    return tuple(WORD.findall(casefold_ascii(value)))


def contains_words(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """Vrai si `needle` apparaît dans `haystack` comme une suite de mots contigus.

    Contigus et dans l'ordre : « Apache Tomcat » ne doit pas se reconnaître dans un texte
    qui cite Apache d'un côté et Tomcat de l'autre. Un motif vide ne reconnaît rien —
    sans quoi un alias sans la moindre lettre apparierait tous les textes.
    """
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[depart:depart + len(needle)] == needle
        for depart in range(len(haystack) - len(needle) + 1)
    )


def no_article_message(category: str) -> str:
    return f"Aucun nouvel article aujourd'hui dans la catégorie {category}."


def no_selection_message(category: str, threshold: int) -> str:
    return (
        f"Aucun article retenu aujourd'hui dans la catégorie {category} "
        f"(score minimal {threshold})."
    )
