"""Orchestration : sélection des catégories, écriture des fichiers, envoi de l'email."""

from __future__ import annotations

import datetime as dt
import pathlib

from rssresume import console
from rssresume.audio import audio_extension
from rssresume.config import AppConfig
from rssresume.models import CategoryDigest
from rssresume.protocols import (
    AudioGeneratorProtocol,
    EmailSenderProtocol,
    FreshRSSClientProtocol,
    SummaryGeneratorProtocol,
)
from rssresume.text import no_article_message, slugify

NO_ARTICLE_SUFFIX = ".no-article"
BODY_SEPARATOR = "\n\n"


class DigestService:
    def __init__(
        self,
        config: AppConfig,
        freshrss_client: FreshRSSClientProtocol,
        summary_generator: SummaryGeneratorProtocol,
        audio_generator: AudioGeneratorProtocol,
        email_sender: EmailSenderProtocol,
    ):
        self._config = config
        self._freshrss_client = freshrss_client
        self._summary_generator = summary_generator
        self._audio_generator = audio_generator
        self._email_sender = email_sender

    def run(self, day: dt.date, send_email: bool = True, mark_read: bool = True) -> list[CategoryDigest]:
        day_dir = self._day_dir(day)
        console.log(f"RSSResume : digest du {day.isoformat()} vers {day_dir}")

        categories = self._select_categories()
        console.log(f"{len(categories)} catégorie(s) à traiter : {', '.join(categories) or '(aucune)'}")

        digests = [self._build_digest(category, day, day_dir) for category in categories]

        if not send_email:
            console.log("Email : ignoré (--dry-run)")
        elif not self._email_sender.is_configured():
            console.log("Email : ignoré (configuration SMTP incomplète)")
        else:
            self._send_email(day, digests)

        if mark_read:
            # Après livraison seulement : un échec d'envoi ne doit pas perdre les articles.
            self._mark_read(digests)
        else:
            console.log("Marquage comme lu : ignoré (--dry-run)")

        console.log(self._report(digests))
        return digests

    @staticmethod
    def _report(digests: list[CategoryDigest]) -> str:
        audios = sum(1 for digest in digests if digest.audio_path)
        articles = sum(len(digest.articles) for digest in digests)
        return (
            f"Terminé : {articles} article(s), {audios} fichier(s) audio, "
            f"{len(digests) - audios} catégorie(s) sans article"
        )

    def _day_dir(self, day: dt.date) -> pathlib.Path:
        """Un sous-répertoire par journée, au format yyyy-MM-dd."""
        return self._config.output_dir / day.isoformat()

    def _select_categories(self) -> list[str]:
        categories = self._config.categories or self._freshrss_client.list_categories()
        excluded = {name.casefold() for name in self._config.excluded_categories}
        return [category for category in categories if category and category.casefold() not in excluded]

    def _build_digest(self, category: str, day: dt.date, day_dir: pathlib.Path) -> CategoryDigest:
        articles = self._freshrss_client.fetch_daily_articles(category, day)
        slug = slugify(category)
        console.category(category, f"{len(articles)} article(s)")

        if not articles:
            # Aucun article : marqueur vide, ni résumé IA ni synthèse vocale.
            marker_path = day_dir / f"{slug}{NO_ARTICLE_SUFFIX}"
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_bytes(b"")
            console.detail(f"aucun article : {marker_path.name} (ni IA ni synthèse vocale)")
            return CategoryDigest(
                category=category,
                articles=articles,
                summary_text=no_article_message(category),
                marker_path=marker_path,
            )

        summary_text = self._summary_generator.summarize(category, articles)
        audio_path = self._audio_generator.synthesize(
            summary_text,
            day_dir / f"{slug}{audio_extension(self._config)}",
        )
        console.detail(f"audio écrit : {audio_path.name} ({audio_path.stat().st_size} octets)")
        return CategoryDigest(
            category=category,
            articles=articles,
            summary_text=summary_text,
            audio_path=audio_path,
        )

    def _mark_read(self, digests: list[CategoryDigest]) -> None:
        articles = [article for digest in digests for article in digest.articles]
        if articles:
            self._freshrss_client.mark_as_read(articles)

    def _send_email(self, day: dt.date, digests: list[CategoryDigest]) -> None:
        body = BODY_SEPARATOR.join(digest.summary_text for digest in digests)
        self._email_sender.send(
            subject=f"Résumé RSS du {day.isoformat()}",
            body=body or f"Aucun article trouvé pour le {day.isoformat()}.",
            attachments=[digest.audio_path for digest in digests if digest.audio_path],
        )
