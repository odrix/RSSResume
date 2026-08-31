"""Point d'entrée en ligne de commande et assemblage des composants."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt

from rssresume import certfr, ephemeride, llm, runlog
from rssresume.audio import AudioGenerator
from rssresume.config import AUDIO_MODES, AppConfig
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.llm import providers
from rssresume.external import mail
from rssresume.montage import MontageService
from rssresume.newsletter import Lettre
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
        ephemeride_service=ephemeride.EphemerideService(
            llm.for_action(providers.EPHEMERIDE)
        ),
        # Construit dans les deux modes, sollicité par le seul mode `global` : un
        # collaborateur qu'on n'appelle pas ne coûte rien, et le service n'a pas à
        # savoir qu'il pourrait être absent.
        montage_service=MontageService(
            llm.for_action(providers.MONTAGE),
            language=config.summary_language,
            profil=config.profil,
            prenom=config.prenom,
        ),
        # Sans fournisseur, et c'est tout l'intérêt : les catégories que
        # `RSSRESUME_CERTFR_CATEGORIES` route n'appellent personne. La liste de
        # composants vient du document de profil, lue au lancement avec lui.
        certfr_service=certfr.CertfrService(config.stack),
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
        "--send-only",
        action="store_true",
        help="Resend the email of an already-produced day from its logs, without any AI call.",
    )
    # Pas de défaut ici non plus : c'est `RSSRESUME_AUDIO_MODE` qui décide, et l'option
    # n'existe que pour essayer l'autre mode sur une journée sans toucher l'environnement
    # du conteneur. Un défaut posé ici l'écraserait à chaque exécution.
    parser.add_argument(
        "--audio-mode",
        choices=AUDIO_MODES,
        help="One audio per category, or a single one for the whole day. "
        "Overrides RSSRESUME_AUDIO_MODE.",
    )
    # `--journal` et non `--log` : « le journal » est le nom métier de ces fichiers dans
    # tout le dépôt, et le franciser à moitié désignerait autre chose que ce que `runlog`
    # appelle un journal.
    parser.add_argument(
        "--journal",
        action="store_true",
        help="Print what an already-produced day says about itself, from its logs. "
        "No AI call, no email, nothing written.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print the day's report at the end of a run, articles included. "
        "Overrides RSSRESUME_DEBUG.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Shorthand for --no-email --no-tags --no-mark-read.",
    )
    return parser.parse_args(argv)


def send_only(config: AppConfig, day: dt.date) -> int:
    """Renvoie l'email d'une journée déjà produite, sans rien recalculer.

    Une journée coûte du scoring, des résumés et de la synthèse vocale. Quand c'est
    l'envoi seul qui a échoué — un port SMTP filtré, une clé d'API refusée, un domaine
    non vérifié — la repayer pour retrouver un texte déjà écrit sur le disque n'a aucun
    sens. Les journaux du jour portent tout ce que l'email montre.

    Ni FreshRSS ni les fournisseurs ne sont sollicités, et rien n'est marqué comme lu :
    le renvoi ne touche à aucun état, il ne fait que réexpédier.
    """
    day_dir = config.output_dir / day.isoformat()
    digests = runlog.read_day(day_dir)
    if not digests:
        console.error(f"Renvoi : aucun journal dans {day_dir}, rien à renvoyer.")
        return 1

    sender = mail.sender(config)
    if not sender.is_configured():
        console.error("Renvoi : configuration d'envoi incomplète, rien n'est envoyé.")
        return 1

    console.log(
        f"Renvoi de l'email du {day.isoformat()} depuis {day_dir} : "
        f"{len(digests)} catégorie(s), aucun appel IA"
    )
    # L'introduction s'ouvre sur AUJOURD'HUI — le jour où la lettre arrive — et non sur
    # la journée qu'elle raconte. Celle du journal ne resert donc que si l'on renvoie le
    # jour même, ce qui est le cas courant ; sinon elle est recalculée localement, sans
    # aucun appel, comme le promet `--send-only`.
    envoi = dt.datetime.now(config.timezone).date()
    lettre = Lettre.compose(
        day,
        digests,
        ephemeride.pour_envoi(runlog.read_ephemeride(day_dir), envoi),
        # Relu du journal de la journée, comme le reste : le mode dans lequel elle a été
        # produite est écrit là, il ne se redemande pas à la configuration du jour. Une
        # journée faite par catégorie n'a pas de montage, et rend `None`.
        montage=runlog.read_montage(day_dir),
    )
    sender.send(
        subject=lettre.subject,
        body=lettre.text,
        attachments=lettre.attachments,
        html=lettre.html,
    )
    return 0


def journal(config: AppConfig, day: dt.date) -> int:
    """Imprime ce qu'une journée déjà produite dit d'elle-même, depuis ses journaux.

    Les fichiers d'une journée vivent dans un volume, sur un serveur où l'on n'entre que
    par SSH. Cette commande répond aux questions qu'on se pose devant une journée qui
    s'est mal passée — quel statut, quel seuil a réellement trié, combien ça a coûté,
    qu'est-ce qui est passé juste à côté — sans avoir à en extraire un fichier.

    Aucun appel, aucun envoi, rien d'écrit : elle ne fait que lire.
    """
    day_dir = config.output_dir / day.isoformat()
    bilan = runlog.lire_bilan(day_dir, day)
    if bilan.vide:
        console.error(f"Journal : aucune trace du {day.isoformat()} dans {day_dir}.")
        return 1
    console.log(bilan.texte(detail=config.debug))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = AppConfig.from_env()
    if args.audio_mode:
        # L'option l'emporte sur l'environnement, et la configuration reste la seule
        # source : tout le monde continue de lire `config.audio_mode`, sans avoir à
        # savoir qu'une ligne de commande existe.
        config = dataclasses.replace(config, audio_mode=args.audio_mode)
    if args.debug:
        config = dataclasses.replace(config, debug=True)
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(config.timezone).date()
    if args.journal:
        # Avant l'assemblage, pour la même raison que le renvoi : lire un journal n'a
        # besoin d'aucun fournisseur, et en exiger un ferait échouer la commande qui sert
        # justement quand quelque chose ne va pas.
        return journal(config, day)
    if args.send_only:
        # Avant l'assemblage : le renvoi n'a besoin d'aucun fournisseur, et en exiger un
        # ferait échouer la seule commande qui sait se passer d'eux.
        if args.dry_run or args.no_email:
            console.error("--send-only n'a rien à faire avec --dry-run ni --no-email.")
            return 2
        return send_only(config, day)

    service = build_service(config, include_read=args.include_read)
    if args.include_read:
        console.log("Articles déjà lus : inclus (--include-read)")
    send_email = not (args.dry_run or args.no_email)
    write_tags = not (args.dry_run or args.no_tags)
    mark_read = not (args.dry_run or args.no_mark_read)
    if args.dry_run:
        console.log("Mode --dry-run : ni email, ni tags, ni marquage comme lu")
    service.run(day, send_email=send_email, write_tags=write_tags, mark_read=mark_read)
    if config.debug:
        # Le bilan est une relecture du répertoire de sortie, pas une décision sur ce que
        # la journée contient : il est ici et non dans `DigestService`. Il emprunte donc
        # exactement le chemin de `--journal`, et ce qu'on lit dans les logs du matin est
        # ce que la commande rejouera le soir.
        bilan = runlog.lire_bilan(config.output_dir / day.isoformat(), day)
        console.log(bilan.texte(detail=True))
    return 0
