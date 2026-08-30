"""Point d'entrée en ligne de commande et assemblage des composants."""

from __future__ import annotations

import argparse
import datetime as dt

from rssresume import llm
from rssresume.audio import AudioGenerator
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.llm import providers
from rssresume.external import mail
from rssresume.summaries import SummaryGenerator
from rssresume.tools import console


def build_service(config: AppConfig, include_read: bool = False) -> DigestService:
    """Assemble le service, un fournisseur par action.

    C'est le seul endroit où les fournisseurs sont choisis : trois actions, trois
    résolutions indépendantes, et `None` là où la clé manque. Le reste du code ne voit
    que des collaborateurs qui savent faire leur travail, ou qui n'existent pas.
    """
    return DigestService(
        config=config,
        freshrss_client=FreshRSSClient(config, include_read=include_read),
        scorer=llm.for_action(providers.SCORING),
        summary_generator=SummaryGenerator(
            llm.for_action(providers.DIGEST),
            language=config.summary_language,
            profil=config.profil,
            char_limit=config.article_char_limit,
        ),
        audio_generator=AudioGenerator(llm.for_action(providers.TTS)),
        email_sender=mail.sender(config),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily FreshRSS audio summaries by category.")
    # Pas de défaut ici : « aujourd'hui » se lit dans le fuseau configuré, que seule la
    # configuration connaît — et l'horloge d'un serveur de cron est souvent en UTC.
    parser.add_argument("--date", help="Date to summarize (YYYY-MM-DD). Defaults to today in RSSRESUME_TIMEZONE.")
    parser.add_argument("--no-email", action="store_true", help="Skip sending the digest email.")
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="Skip writing FreshRSS tags (score-NN, scoring-<hash>, digested).",
    )
    parser.add_argument(
        "--no-mark-read",
        action="store_true",
        help="Leave articles unread in FreshRSS. Scores are still written, so they are not recomputed.",
    )
    parser.add_argument(
        "--include-read",
        action="store_true",
        help="Fetch articles already marked as read, which the API excludes by default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Shorthand for --no-email --no-tags --no-mark-read.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = AppConfig.from_env()
    service = build_service(config, include_read=args.include_read)
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(config.timezone).date()
    if args.include_read:
        console.log("Articles déjà lus : inclus (--include-read)")
    send_email = not (args.dry_run or args.no_email)
    write_tags = not (args.dry_run or args.no_tags)
    mark_read = not (args.dry_run or args.no_mark_read)
    if args.dry_run:
        console.log("Mode --dry-run : ni email, ni tags, ni marquage comme lu")
    service.run(day, send_email=send_email, write_tags=write_tags, mark_read=mark_read)
    return 0
