"""Point d'entrée en ligne de commande et assemblage des composants."""

from __future__ import annotations

import argparse
import datetime as dt

from rssresume import console
from rssresume.audio import AudioGenerator
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.freshrss import FreshRSSClient
from rssresume.mailer import EmailSender
from rssresume.summaries import SummaryGenerator


def build_service(config: AppConfig) -> DigestService:
    return DigestService(
        config=config,
        freshrss_client=FreshRSSClient(config),
        summary_generator=SummaryGenerator(config),
        audio_generator=AudioGenerator(config),
        email_sender=EmailSender(config),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily FreshRSS audio summaries by category.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Date to summarize (YYYY-MM-DD).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate summaries and audio without sending email nor marking articles as read.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = AppConfig.from_env()
    service = build_service(config)
    day = dt.date.fromisoformat(args.date)
    if args.dry_run:
        console.log("Mode --dry-run : ni email ni marquage comme lu")
    service.run(day, send_email=not args.dry_run, mark_read=not args.dry_run)
    return 0
