"""Utilitaires de texte partagés par les différents modules."""

from __future__ import annotations

import re
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


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "category"


def no_article_message(category: str) -> str:
    return f"Aucun nouvel article aujourd'hui dans la catégorie {category}."


def no_selection_message(category: str, threshold: int) -> str:
    return (
        f"Aucun article retenu aujourd'hui dans la catégorie {category} "
        f"(score minimal {threshold})."
    )
