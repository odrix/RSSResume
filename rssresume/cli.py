"""Point d'entrée en ligne de commande et assemblage des composants."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt

from rssresume import certfr, ephemeride, llm, runlog
from rssresume.audio import AudioGenerator
from rssresume.config import AUDIO_MODES, AppConfig, _split_categories
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.llm import providers
from rssresume.external import mail
from rssresume.montage import MontageService
from rssresume.newsletter import Lettre
from rssresume.profil import Annuaire
from rssresume.summaries import SummaryGenerator
from rssresume.tournee import Tournee
from rssresume.tools import console


def build_service(
    config: AppConfig,
    include_read: bool = False,
    freshrss_client: FreshRSSClient | None = None,
) -> DigestService:
    """Assemble le service, un fournisseur par action.

    C'est le seul endroit où les fournisseurs sont choisis : trois actions, trois
    résolutions indépendantes, et `None` là où la clé manque. Le reste du code ne voit
    que des collaborateurs qui savent faire leur travail, ou qui n'existent pas.

    `freshrss_client` est celui de la tournée, partagé entre les profils : il est
    décliné au nom de la personne servie, pour qu'elle tague sous son préfixe tout en
    relisant les articles que la tournée a déjà lus.
    """
    if freshrss_client is None:
        freshrss_client = FreshRSSClient(config, include_read=include_read)
    else:
        freshrss_client = freshrss_client.pour(config.username)
    return DigestService(
        config=config,
        freshrss_client=freshrss_client,
        scorer=llm.for_action(providers.SCORING),
        summary_generator=SummaryGenerator(
            llm.for_action(providers.DIGEST),
            language=config.summary_language,
            profil=config.profil,
            char_limit=config.article_char_limit,
            # La même stack que celle des avis CERT-FR, et lue au même endroit : elle ne
            # décide ici d'aucune sélection, seulement du détail donné sur les versions
            # d'une CVE selon qu'elle touche ou non ce qu'on exploite.
            stack=config.stack,
            # Et le régime de sécurité du même document, qui dit qui écoute ce détail.
            securite=config.securite,
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
            # Il lit maintenant les mêmes articles que le résumé de catégorie : mêmes
            # bornes d'entrée, et la même stack pour graduer le détail des versions.
            char_limit=config.article_char_limit,
            stack=config.stack,
            securite=config.securite,
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
    # Sans défaut : sans l'option, tous les profils de l'annuaire sont servis.
    parser.add_argument(
        "--profil",
        metavar="USERNAME",
        help="Only this profile (its file name without extension). Defaults to every profile.",
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
    # Ajout des options pour les catégories
    parser.add_argument(
        "--categories",
        metavar="A,B",
        help="Traiter seulement ces catégories, séparées par des virgules, au lieu de RSSRESUME_CATEGORIES.",
    )
    parser.add_argument(
        "--limit",
        type=_entier_positif,
        metavar="N",
        help="Limiter à N articles chaque catégorie pour le scoring et le résumé.",
    )
    return parser.parse_args(argv)


def _entier_positif(value: str) -> int:
    """Le nombre d'articles du CLI : nul ou négatif est une commande impossible."""
    try:
        nombre = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("doit être un entier positif") from exc
    if nombre < 1:
        raise argparse.ArgumentTypeError("doit être un entier positif")
    return nombre


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
    if args.categories:
        config = dataclasses.replace(
            config,
            categories_surcharge=_split_categories(args.categories, "--categories"),
        )
    if args.limit:
        config = dataclasses.replace(config, limite_articles=args.limit)
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(config.timezone).date()
    # Lu au lancement, comme la configuration : deux sources de profils posées ensemble
    # ou un `--profil` inconnu échouent avant toute lecture et tout appel.
    annuaire = Annuaire.depuis_env()
    cibles = annuaire.cibles(args.profil)
    if args.journal:
        # Avant l'assemblage, pour la même raison que le renvoi : lire un journal n'a
        # besoin d'aucun fournisseur, et en exiger un ferait échouer la commande qui sert
        # justement quand quelque chose ne va pas.
        return _par_profil(config, annuaire, cibles, lambda profil: journal(profil, day))
    if args.send_only:
        # Avant l'assemblage : le renvoi n'a besoin d'aucun fournisseur, et en exiger un
        # ferait échouer la seule commande qui sait se passer d'eux.
        if args.dry_run or args.no_email:
            console.error("--send-only n'a rien à faire avec --dry-run ni --no-email.")
            return 2
        return _par_profil(config, annuaire, cibles, lambda profil: send_only(profil, day))

    if args.include_read:
        console.log("Articles déjà lus : inclus (--include-read)")
    send_email = not (args.dry_run or args.no_email)
    write_tags = not (args.dry_run or args.no_tags)
    mark_read = not (args.dry_run or args.no_mark_read)
    if args.dry_run:
        console.log("Mode --dry-run : ni email, ni tags, ni marquage comme lu")

    client_freshrss = FreshRSSClient(config, include_read=args.include_read)
    if args.categories:
        try:
            disponibles = client_freshrss.list_categories()
            config.categories_servies(disponibles)
        except ValueError as exc:
            console.error(f"Tournée : {exc}")
            return 2
        except Exception as exc:  # noqa: BLE001 — impossible de vérifier --categories si FreshRSS est indisponible
            console.error(f"Tournée : impossible de vérifier --categories ({exc!r})")
            return 2

    tournee = Tournee(
        config,
        annuaire,
        client_freshrss,
        lambda profil, client: build_service(profil, freshrss_client=client),
    )
    try:
        echecs = tournee.run(
            day, args.profil, send_email=send_email, write_tags=write_tags, mark_read=mark_read
        )
    except ValueError as exc:
        # Le catalogue refusé ou corrompu : un message qui dit quoi faire, pas une trace
        # de pile. Un profil fautif, lui, n'arrive pas jusqu'ici — la tournée l'isole.
        console.error(f"Tournée : {exc}")
        return 2
    return 1 if echecs else 0


def _par_profil(config: AppConfig, annuaire: Annuaire, cibles: list[str], commande) -> int:
    """Une commande de relecture (`--journal`, `--send-only`) jouée profil par profil.

    Un profil en échec n'arrête pas les autres ; le code de sortie dit qu'il y en a eu.
    """
    code = 0
    for nom in cibles:
        if len(cibles) > 1:
            console.log(f"── Profil « {nom} »")
        try:
            code = max(code, commande(config.pour(annuaire.lecteur(nom))))
        except ValueError as exc:
            console.error(f"Profil « {nom} » : {exc}")
            code = max(code, 1)
    return code
