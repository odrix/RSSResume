"""Génération des résumés textuels par catégorie."""

from __future__ import annotations

import json

from rssresume import console
from rssresume.config import AppConfig
from rssresume.llm import post_json
from rssresume.models import Article
from rssresume.text import no_article_message

ERROR_LABEL = "OpenAI-compatible summary"
EXCERPT_LENGTH = 800
FALLBACK_ARTICLES = 5
FALLBACK_EXCERPT_LENGTH = 180

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
                "excerpt": article.content_text[:EXCERPT_LENGTH],
            }
            for article in articles
        ]
        payload = {
            "model": self._config.summary_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_prompt(category, prompt_articles)},
            ],
        }
        console.detail(f"résumé via l'API {self._config.summary_model} ({len(articles)} article(s))")
        response = post_json(
            self._config.llm_base_url,
            self._config.llm_api_key,
            "/chat/completions",
            payload,
            ERROR_LABEL,
        )
        return response["choices"][0]["message"]["content"].strip()

    def _user_prompt(self, category: str, prompt_articles: list[dict]) -> str:
        return (
            f"Résume les articles du jour pour la catégorie '{category}' en {self._config.summary_language}. "
            "Fais un court paragraphe d'introduction, puis 3 à 6 points clés maximum, "
            "et une phrase de conclusion." + "\n\n"
            "Articles:\n" + json.dumps(prompt_articles, ensure_ascii=False)
        )

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
