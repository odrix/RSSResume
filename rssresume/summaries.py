"""Le résumé d'une catégorie : celui du fournisseur, ou le repli extractif local.

Le générateur ne sait rien du fournisseur au-delà de son contrat : il reçoit un
`LLMProvider`, ou `None`, et c'est alors le repli. Les prompts vivent dans
`llm/prompts.py`, la mise en forme du digest est ici, et la requête chez l'adaptateur.
"""

from __future__ import annotations

from rssresume.certfr import Stack
from rssresume.config import DEFAULT_ARTICLE_CHAR_LIMIT
from rssresume.llm import LLMProvider
from rssresume.models import Article, Note
from rssresume.profil import SECURITE_PAR_DEFAUT, Securite
from rssresume.tools import console
from rssresume.tools.text import no_article_message, truncate_sentences

FALLBACK_ARTICLES = 5
FALLBACK_EXCERPT_LENGTH = 180


class SummaryGenerator:
    """Résume une catégorie. Sans fournisseur, un extractif local qui s'entend aussi bien."""

    def __init__(self, provider: LLMProvider | None = None, language: str = "fr",
                 profil: str | None = None,
                 char_limit: int = DEFAULT_ARTICLE_CHAR_LIMIT,
                 stack: Stack | None = None,
                 securite: Securite = SECURITE_PAR_DEFAUT):
        self._provider = provider
        self._language = language
        self._profil = profil
        #: Plafond de caractères par article. Le résumé était le seul chemin sans borne
        #: d'entrée du pipeline : douze articles de fond partaient intégralement.
        self._char_limit = char_limit
        #: La même liste de composants que celle des avis CERT-FR, et pour le même usage :
        #: répondre « est-ce que ça me touche ». Ici elle ne trie rien, l'article est
        #: raconté dans tous les cas, elle règle seulement le détail donné sur les
        #: versions d'une CVE. Vide, le résumé reste au régime d'avant : tout, pour toutes.
        self._stack = stack if stack is not None else Stack()
        #: Le régime de sécurité du document : la stack dit ce qui tourne, lui dit qui
        #: écoute, et les deux ensemble règlent ce qu'une CVE garde de ses versions.
        self._securite = securite

    def summarize(
        self, category: str, articles: list[Article], notes: dict[str, Note] | None = None
    ) -> str:
        if not articles or self._provider is None:
            return self._summarize_fallback(category, articles)

        # Les avis de vulnérabilité arrivent enrichis du texte de leur page : c'est
        # `digest.py` qui la lit, une fois, avant de partager les mêmes articles entre le
        # résumé de la catégorie et l'audio de journée. Le faire ici allait la chercher
        # deux fois et laissait l'un des deux lecteurs travailler sur le seul titre.
        notes = notes or {}
        payload = [self._to_payload(article, notes.get(article.item_id)) for article in articles]
        volume = sum(len(item["content"]) for item in payload)
        tronques = sum(
            1
            for article, item in zip(articles, payload)
            if len(item["content"]) < len(article.content_text)
        )
        console.detail(
            f"résumé via {self._provider.name}, {self._provider.model('digest')} "
            f"({len(articles)} article(s), {volume} caractère(s) envoyés"
            + (f", {tronques} tronqué(s) à {self._char_limit})" if tronques else ")")
        )
        return self._provider.write_digest(
            category,
            payload,
            self._language,
            self._profil,
            not self._stack.vide,
            # Par mot-clé : ce qui précède est le contrat historique, que les doublures
            # des tests relisent par position.
            securite=self._securite,
        )

    def _to_payload(self, article: Article, note: Note | None) -> dict:
        """Article tel qu'il part au résumeur : son contenu, plus ce que le scoring en sait.

        Le score, l'angle et la thématique sont déjà payés par le scoring. Les jeter
        obligeait le résumeur à redécouvrir seul pourquoi chaque article était là, et à
        quel point s'y attarder.
        """
        payload = {
            "title": article.title,
            # Ni URL ni nom de flux : ce qui n'est pas dans le contexte ne peut pas être
            # prononcé. L'auditeur ne veut pas du média, et une URL vue dans le contexte
            # est une URL que le modèle peut recopier de travers. Les liens et les sources
            # de l'email viennent de `CategoryDigest.links`, pas du texte produit ici.
            # Plafonné, et coupé à la phrase : le scoring lisait 400 caractères par
            # article quand le résumé en envoyait le texte entier, douze fois.
            "content": truncate_sentences(article.content_text, self._char_limit),
        }
        # Apparié sur le titre ET le contenu, comme les avis CERT-FR : un billet
        # « Multiples vulnérabilités dans les produits IBM » ne nomme le composant
        # réellement touché que dans son texte. Le champ est absent quand rien ne
        # correspond, et c'est cette absence que le prompt lit.
        concernes = self._stack.concernes(f"{article.title}\n{article.content_text}")
        if concernes:
            payload["stack"] = list(concernes)
        if note:
            payload["score"] = note.score
            payload["thematique"] = note.thematique
            if note.angle:
                # Absent des articles dont le score vient du cache de tags.
                payload["angle"] = note.angle
        return payload

    @staticmethod
    def _summarize_fallback(category: str, articles: list[Article]) -> str:
        if not articles:
            return no_article_message(category)

        console.detail(f"résumé local, sans IA ({len(articles)} article(s))")
        # Des phrases enchaînées, comme la version IA : ce texte part aussi en synthèse vocale.
        sentences = [
            f"Résumé du jour pour la catégorie {category}, {len(articles)} article(s) aujourd'hui."
        ]
        for article in articles[:FALLBACK_ARTICLES]:
            excerpt = article.content_text[:FALLBACK_EXCERPT_LENGTH].rstrip()
            # Pas plus de nom de flux ici que dans la version IA : la règle vient de
            # l'auditeur, pas du moteur, et les deux textes partent au même TTS.
            sentences.append(f"{article.title} : {excerpt}." if excerpt else f"{article.title}.")
        if len(articles) > FALLBACK_ARTICLES:
            sentences.append(
                f"{len(articles) - FALLBACK_ARTICLES} autre(s) article(s) complètent cette catégorie."
            )
        sentences.append("Bonne journée.")
        return " ".join(sentences)
