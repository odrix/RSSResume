"""Configuration de l'application, lue depuis l'environnement.

Ce qui concerne les fournisseurs de LLM n'est plus ici : leurs réglages vivent dans
`llm/providers.json`, leur choix et leurs clés dans `llm/providers.py`. Il ne reste donc que
ce qui est propre à cette installation — FreshRSS, les catégories, le seuil, le SMTP.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import pathlib
import zoneinfo

from rssresume.models import SelectionRule
from rssresume.profil import load_profil

#: Fuseau qui découpe les journées. Les bornes se calculaient en UTC : en heure d'été, un
#: article publié à 1 h du matin à Paris tombait dans la veille et n'apparaissait dans
#: aucun digest — un décalage muet, invisible tant qu'on ne le cherche pas.
ENV_TIMEZONE = "RSSRESUME_TIMEZONE"
DEFAULT_TIMEZONE = "Europe/Paris"

#: Plafond de caractères par article sur le chemin du résumé. Le scoring est borné à 400
#: caractères depuis toujours ; le résumé, lui, envoyait le texte intégral de douze
#: articles, soit facilement cent mille caractères sans le moindre garde-fou. Huit mille
#: laissent passer entier un avis de sécurité enrichi par `tools/cve.py`, qui en lit six
#: mille au plus — c'est là que sont les versions touchées, et rien ne doit les couper.
ENV_ARTICLE_CHAR_LIMIT = "RSSRESUME_ARTICLE_CHAR_LIMIT"
DEFAULT_ARTICLE_CHAR_LIMIT = 8000


def load_timezone(name: str | None = None) -> dt.tzinfo:
    """Le fuseau nommé, résolu au lancement : un nom inconnu doit échouer tout de suite.

    `zoneinfo` lit la base de fuseaux du système. Windows n'en fournit pas, d'où le paquet
    `tzdata` en dépendance : le dire dans le message évite de chercher une demi-heure.
    """
    nom = (name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return zoneinfo.ZoneInfo(nom)
    except (KeyError, ValueError, OSError) as exc:
        raise ValueError(
            f"{ENV_TIMEZONE} : fuseau « {nom} » introuvable ({exc}). Vérifier le nom "
            f"(par exemple {DEFAULT_TIMEZONE}) et, sur un système sans base de fuseaux — "
            "Windows en tête — que le paquet `tzdata` est installé."
        ) from exc


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return (value or "").strip() or None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_thresholds(value: str | None, name: str) -> dict[str, int]:
    """`Catégorie=score, Autre=score` → seuils par catégorie, clés repliées en casse.

    Une entrée mal formée lève au lancement plutôt que d'être ignorée : un seuil qu'on
    croit posé sur une catégorie et qui ne l'est pas ne se voit qu'au bout de plusieurs
    digests trop courts, et pour la même raison que le fichier de profil illisible.
    """
    seuils: dict[str, int] = {}
    for item in _split_csv(value):
        categorie, _, score = item.rpartition("=")
        if not categorie.strip() or not score.strip().isdigit():
            raise ValueError(f"{name} : « {item} » n'est pas de la forme « Catégorie=score »")
        seuils[categorie.strip().casefold()] = int(score.strip())
    return seuils


@dataclasses.dataclass(frozen=True)
class AppConfig:
    freshrss_base_url: str
    freshrss_username: str
    freshrss_api_password: str
    output_dir: pathlib.Path
    categories: list[str]
    excluded_categories: list[str]
    summary_language: str
    #: Fuseau dans lequel une « journée » commence et finit, pour FreshRSS comme pour la
    #: date par défaut de la ligne de commande.
    timezone: dt.tzinfo
    #: Profil de pertinence : le texte qui définit ce qui mérite d'être noté et raconté.
    #: Résolu une fois au démarrage — un fichier de profil illisible doit faire échouer
    #: le lancement, pas la troisième catégorie.
    profil: str
    #: Score minimal pour qu'un article entre dans le digest.
    score_threshold: int
    #: Seuils propres à certaines catégories, qui l'emportent sur `score_threshold`.
    #: Clés repliées en casse. Une catégorie généraliste, où tout est intéressant sans
    #: être actionnable, ne se juge pas au même seuil qu'un flux d'avis de sécurité.
    category_thresholds: dict[str, int]
    #: Seuil de repli, appliqué à la journée entière quand le seuil normal retient
    #: moins de `min_digest_items` articles.
    fallback_threshold: int
    #: Nombre de retenus en dessous duquel le seuil de repli s'applique. `0` le désactive.
    min_digest_items: int
    #: Nombre maximum d'articles retenus par catégorie.
    max_digest_items: int
    #: Plafond de caractères envoyés au résumeur par article. `0` le désactive.
    article_char_limit: int
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
            timezone=load_timezone(_env(ENV_TIMEZONE)),
            profil=load_profil(),
            score_threshold=int(_env("RSSRESUME_SCORE_THRESHOLD", "7") or "7"),
            category_thresholds=_split_thresholds(
                _env("RSSRESUME_CATEGORY_THRESHOLDS"), "RSSRESUME_CATEGORY_THRESHOLDS"
            ),
            fallback_threshold=int(_env("RSSRESUME_FALLBACK_THRESHOLD", "5") or "5"),
            min_digest_items=int(_env("RSSRESUME_MIN_DIGEST_ITEMS", "5") or "5"),
            max_digest_items=int(_env("RSSRESUME_MAX_DIGEST_ITEMS", "12") or "12"),
            article_char_limit=int(
                _env(ENV_ARTICLE_CHAR_LIMIT, str(DEFAULT_ARTICLE_CHAR_LIMIT))
                or DEFAULT_ARTICLE_CHAR_LIMIT
            ),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=int(_env("SMTP_PORT", "587") or "587"),
            smtp_username=_env("SMTP_USERNAME"),
            smtp_password=_env("SMTP_PASSWORD"),
            smtp_from=_env("SMTP_FROM"),
            smtp_to=_split_csv(_env("SMTP_TO")),
            smtp_use_tls=(_env("SMTP_USE_TLS", "true") or "").lower() == "true",
            smtp_use_ssl=(_env("SMTP_USE_SSL", "false") or "").lower() == "true",
        )

    def selection_rule(self, category: str) -> SelectionRule:
        """La règle de sélection d'une catégorie : son seuil, son repli, son plafond.

        Le seuil est le seul réglage qui se surcharge par catégorie. Le repli et le
        plafond, eux, valent pour toutes : ils répondent au volume d'une journée, pas
        à la nature d'un flux.
        """
        return SelectionRule(
            seuil=self.category_thresholds.get(category.casefold(), self.score_threshold),
            seuil_repli=self.fallback_threshold,
            minimum=self.min_digest_items,
            plafond=self.max_digest_items,
        )
