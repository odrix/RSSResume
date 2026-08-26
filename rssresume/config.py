"""Configuration de l'application, lue depuis l'environnement.

Ce qui concerne les fournisseurs de LLM n'est plus ici : leurs réglages vivent dans
`llm/providers.json`, leur choix et leurs clés dans `llm/providers.py`. Il ne reste donc que
ce qui est propre à cette installation — FreshRSS, les catégories, le seuil, le SMTP.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib

from rssresume.profil import load_profil


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return (value or "").strip() or None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclasses.dataclass(frozen=True)
class AppConfig:
    freshrss_base_url: str
    freshrss_username: str
    freshrss_api_password: str
    output_dir: pathlib.Path
    categories: list[str]
    excluded_categories: list[str]
    summary_language: str
    #: Profil de pertinence : le texte qui définit ce qui mérite d'être noté et raconté.
    #: Résolu une fois au démarrage — un fichier de profil illisible doit faire échouer
    #: le lancement, pas la troisième catégorie.
    profil: str
    #: Score minimal pour qu'un article entre dans le digest.
    score_threshold: int
    #: Nombre maximum d'articles retenus par catégorie.
    max_digest_items: int
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from: str | None
    smtp_to: list[str]
    smtp_use_tls: bool
    smtp_use_ssl: bool

    @classmethod
    def from_env(cls) -> "AppConfig":
        base_url = _env("FRESHRSS_BASE_URL")
        username = _env("FRESHRSS_USERNAME")
        api_password = _env("FRESHRSS_API_PASSWORD")
        missing = [
            name
            for name, value in (
                ("FRESHRSS_BASE_URL", base_url),
                ("FRESHRSS_USERNAME", username),
                ("FRESHRSS_API_PASSWORD", api_password),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return cls(
            freshrss_base_url=base_url,
            freshrss_username=username,
            freshrss_api_password=api_password,
            output_dir=pathlib.Path(_env("RSSRESUME_OUTPUT_DIR") or "output"),
            categories=_split_csv(_env("RSSRESUME_CATEGORIES")),
            excluded_categories=_split_csv(_env("RSSRESUME_EXCLUDED_CATEGORIES")),
            summary_language=_env("RSSRESUME_SUMMARY_LANGUAGE", "fr") or "fr",
            profil=load_profil(),
            score_threshold=int(_env("RSSRESUME_SCORE_THRESHOLD", "7") or "7"),
            max_digest_items=int(_env("RSSRESUME_MAX_DIGEST_ITEMS", "12") or "12"),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=int(_env("SMTP_PORT", "587") or "587"),
            smtp_username=_env("SMTP_USERNAME"),
            smtp_password=_env("SMTP_PASSWORD"),
            smtp_from=_env("SMTP_FROM"),
            smtp_to=_split_csv(_env("SMTP_TO")),
            smtp_use_tls=(_env("SMTP_USE_TLS", "true") or "").lower() == "true",
            smtp_use_ssl=(_env("SMTP_USE_SSL", "false") or "").lower() == "true",
        )
