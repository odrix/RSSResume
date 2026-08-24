"""Génération des résumés textuels par catégorie."""

from __future__ import annotations

import json

from rssresume import console
from rssresume.config import AppConfig
from rssresume import llm
from rssresume.models import Article
from rssresume.text import no_article_message

FALLBACK_ARTICLES = 5
FALLBACK_EXCERPT_LENGTH = 180

#: Nombre de points clés demandés, par palier de volume d'articles.
BULLET_TIERS = (
    (5, "2 à 3 points clés"),
    (15, "3 à 6 points clés"),
    (35, "6 à 10 points clés, regroupés par thème"),
)
BULLET_DEFAULT = "8 à 12 points clés, regroupés par thème, en signalant les sujets majeurs"

SYSTEM_PROMPT = (
    "Tu rédiges des résumés audio quotidiens de flux RSS. "
    "Réponds dans une langue naturelle, concise, adaptée à une lecture vocale."
)


class SummaryGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def summarize(self, category: str, articles: list[Article]) -> str:
        if not articles:
            return self._summarize_fallback(category, articles)
        if self._config.uses_llm:
            return self._summarize_with_openai(category, articles)
        return self._summarize_fallback(category, articles)

    def _summarize_with_openai(self, category: str, articles: list[Article]) -> str:
        prompt_articles = [
            {
                "title": article.title,
                "feed": article.feed_title,
                "url": article.url,
                "content": article.content_text,
            }
            for article in articles
        ]
        console.detail(f"résumé via l'API {self._config.summary_model} ({len(articles)} article(s))")
        return llm.chat(
            self._config.llm_base_url,
            self._config.llm_api_key,
            llm.DIGEST,
            SYSTEM_PROMPT,
            self._user_prompt(category, prompt_articles, len(articles)),
            model=self._config.summary_model,
        )

    def _user_prompt(self, category: str, prompt_articles: list[dict], article_count: int) -> str:
        return (
            f"Résume les articles du jour pour la catégorie '{category}' en {self._config.summary_language}. "
            f"Fais un court paragraphe d'introduction, puis {self._bullet_instruction(article_count)}, "
            "et une phrase de conclusion." + "\n\n"
            "Articles:\n" + json.dumps(prompt_articles, ensure_ascii=False)
        )

    @staticmethod
    def _bullet_instruction(article_count: int) -> str:
        """Nombre de points clés proportionné au volume : 6 points pour 50 articles diluent tout."""
        for threshold, instruction in BULLET_TIERS:
            if article_count <= threshold:
                return instruction
        return BULLET_DEFAULT

    @staticmethod
    def _summarize_fallback(category: str, articles: list[Article]) -> str:
        if not articles:
            return no_article_message(category)

        console.detail(f"résumé local, sans IA ({len(articles)} article(s))")
        lines = [f"Résumé quotidien pour la catégorie {category}. {len(articles)} article(s) aujourd'hui."]
        for article in articles[:FALLBACK_ARTICLES]:
            excerpt = article.content_text[:FALLBACK_EXCERPT_LENGTH].rstrip()
            if excerpt:
                lines.append(f"- {article.title} ({article.feed_title}) : {excerpt}.")
            else:
                lines.append(f"- {article.title} ({article.feed_title}).")
        if len(articles) > FALLBACK_ARTICLES:
            lines.append(f"- {len(articles) - FALLBACK_ARTICLES} autre(s) article(s) complètent cette catégorie.")
        lines.append("Fin du résumé du jour.")
        return "\n".join(lines)
