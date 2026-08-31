"""Configuration de l'application, lue depuis l'environnement.

Ce qui concerne les fournisseurs de LLM n'est plus ici : leurs réglages vivent dans
`llm/providers.json`, leur choix et leurs clés dans `llm/providers.py`. Ce qui est propre à
la personne non plus — profil de pertinence, stack surveillée, destinataire du digest sont
dans un document unique que `profil.py` lit (`RSSRESUME_PROFILE_FILE`). Il ne reste donc ici
que ce qui est propre à cette installation : FreshRSS, les catégories, le seuil, le transport
du courrier.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import pathlib
import zoneinfo

from rssresume.certfr.stack import Stack
from rssresume.models import SelectionRule
from rssresume.profil import CLE_EMAIL, ENV_PROFIL_FILE, load_profil
from rssresume.tools.text import casefold_ascii, words

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

#: Par où part le digest. Le SMTP est le chemin naturel, mais beaucoup d'hébergeurs
#: filtrent 25, 465 et 587 en sortie : `resend` passe alors par le 443, qui sort
#: forcément. Les noms sont déclarés ici, et non dans `external/mail.py` qui les fait
#: correspondre à leur implémentation, pour qu'un réglage fautif fasse échouer le
#: lancement — un conteneur qui ne démarre pas se voit, un matin sans digest non.
ENV_MAIL_TRANSPORT = "RSSRESUME_MAIL_TRANSPORT"
MAIL_TRANSPORT_SMTP = "smtp"
MAIL_TRANSPORT_RESEND = "resend"
MAIL_TRANSPORTS = (MAIL_TRANSPORT_SMTP, MAIL_TRANSPORT_RESEND)
DEFAULT_MAIL_TRANSPORT = MAIL_TRANSPORT_SMTP

#: La clé d'API de Resend, nommée d'après le service comme celles des fournisseurs de LLM.
ENV_RESEND_API_KEY = "RESEND_API_KEY"

#: Le destinataire du digest se lisait ici ; il est passé dans le document de profil,
#: avec le reste de ce qui est personnel. La variable est **refusée** et non ignorée :
#: laissée en place dans un environnement déjà déployé, elle ferait croire qu'un
#: destinataire est configuré, et le digest ne partirait plus sans que rien ne le dise.
ENV_SMTP_TO = "SMTP_TO"

#: Catégories routées vers le traitement déterministe des avis CERT-FR (`rssresume/certfr/`)
#: au lieu du scoring, du résumé et de la synthèse vocale. Le routage est explicite et non
#: déduit du nom de la catégorie : rien ne doit changer de pipeline parce que quelqu'un a
#: renommé un dossier FreshRSS. Vide — le défaut — laisse tout au chemin habituel.
ENV_CERTFR_CATEGORIES = "RSSRESUME_CERTFR_CATEGORIES"

#: Comment la journée est mise en voix. `category` — le défaut — rend un mp3 par
#: catégorie ; `global` n'en rend qu'un, qui raconte la journée entière. Le second ne
#: remplace pas les résumés de catégorie : il les relit pour les enchaîner, et l'email
#: continue de montrer les siens, mot pour mot. Les valeurs sont en anglais comme celles
#: de `RSSRESUME_MAIL_TRANSPORT` — ce qui se tape dans l'environnement suit la langue des
#: variables, pas celle du code métier.
ENV_AUDIO_MODE = "RSSRESUME_AUDIO_MODE"
AUDIO_MODE_CATEGORY = "category"
AUDIO_MODE_GLOBAL = "global"
AUDIO_MODES = (AUDIO_MODE_CATEGORY, AUDIO_MODE_GLOBAL)
DEFAULT_AUDIO_MODE = AUDIO_MODE_CATEGORY


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


def load_mail_transport(name: str | None = None) -> str:
    """Le transport nommé, validé au lancement : un nom inconnu ne doit pas attendre.

    Une faute de frappe qu'on laisserait passer retomberait silencieusement sur le SMTP,
    c'est-à-dire sur le chemin que l'on cherchait précisément à éviter.
    """
    transport = (name or DEFAULT_MAIL_TRANSPORT).strip().lower() or DEFAULT_MAIL_TRANSPORT
    if transport not in MAIL_TRANSPORTS:
        raise ValueError(
            f"{ENV_MAIL_TRANSPORT} : transport « {transport} » inconnu. "
            f"Valeurs acceptées : {', '.join(MAIL_TRANSPORTS)}."
        )
    return transport


def load_audio_mode(name: str | None = None) -> str:
    """Le mode nommé, validé au lancement : un nom inconnu ne doit pas attendre le soir.

    Même arbitrage que le transport du courrier. Une faute de frappe ignorée retomberait
    sur le mode par catégorie, c'est-à-dire précisément sur celui qu'on voulait quitter —
    et rien ne le dirait avant la boîte aux lettres, sept mp3 plus tard.
    """
    mode = (name or DEFAULT_AUDIO_MODE).strip().lower() or DEFAULT_AUDIO_MODE
    if mode not in AUDIO_MODES:
        raise ValueError(
            f"{ENV_AUDIO_MODE} : mode « {mode} » inconnu. "
            f"Valeurs acceptées : {', '.join(AUDIO_MODES)}."
        )
    return mode


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


def _split_categories(value: str | None, name: str) -> list[str]:
    """`Catégorie, Autre` → les libellés, une entrée mal formée levant au lancement.

    Deux fautes se ressemblent assez pour arriver, et aucune des deux ne se verrait
    autrement qu'à l'usage : recopier la forme de `RSSRESUME_CATEGORY_THRESHOLDS` —
    « Catégorie=7 » là où seul le libellé est attendu — et laisser une entrée qui ne
    porte pas un mot, reste d'une liste à demi effacée. Dans les deux cas la catégorie
    ne serait jamais routée, et le digest continuerait de la passer au LLM sans rien
    dire. Même arbitrage que les seuils par catégorie : on lève.
    """
    libelles = []
    for item in _split_csv(value):
        if "=" in item:
            raise ValueError(
                f"{name} : « {item} » n'est qu'un libellé de catégorie à recopier, sans "
                "« = » ni valeur — cette variable ne prend pas de réglage par catégorie"
            )
        if not words(item):
            raise ValueError(f"{name} : « {item} » ne porte ni lettre ni chiffre")
        libelles.append(item)
    return libelles


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
    #: Les destinataires du digest, déclarés dans le document de profil : à qui la
    #: lettre est adressée est une donnée de la personne, pas un réglage de transport.
    #: Le nom reste celui de l'en-tête d'un email, que les deux transports écrivent.
    smtp_to: list[str]
    smtp_use_tls: bool
    smtp_use_ssl: bool
    #: Par où part le digest : `smtp` ou `resend`. Les adresses, elles, restent celles de
    #: `SMTP_FROM` et `SMTP_TO` — expéditeur et destinataires ne changent pas de nature
    #: parce que le transport change.
    mail_transport: str = DEFAULT_MAIL_TRANSPORT
    resend_api_key: str | None = None
    #: Catégories routées hors du pipeline LLM, vers le traitement déterministe des avis
    #: CERT-FR. Les libellés sont gardés tels qu'ils ont été écrits — c'est
    #: `est_deterministe` qui les replie pour comparer, et le journal n'a rien à y lire.
    certfr_categories: list[str] = dataclasses.field(default_factory=list)
    #: Les composants surveillés, déclarés dans le même document que le profil et lus au
    #: même moment : un document fautif fait échouer le lancement, pas la catégorie
    #: d'avis d'un matin. Vide par défaut — c'est l'état de qui vient d'installer l'outil,
    #: et la phrase du digest le dit.
    stack: Stack = dataclasses.field(default_factory=Stack)
    #: Le prénom de la personne, déclaré dans le même document que le profil : c'est avec
    #: lui que l'audio de journée ouvre. Facultatif — sans lui, le montage ouvre sans
    #: nommer personne, et rien d'autre ne change.
    prenom: str = ""
    #: Comment la journée est mise en voix : un audio par catégorie, ou un seul pour tout.
    audio_mode: str = DEFAULT_AUDIO_MODE

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

        if _env(ENV_SMTP_TO):
            raise ValueError(
                f"{ENV_SMTP_TO} n'est plus lu : le destinataire du digest se déclare à la "
                f"clé « {CLE_EMAIL} » du document de profil ({ENV_PROFIL_FILE}), avec le "
                "profil de pertinence et la stack. Retirer la variable de l'environnement."
            )

        #: Tout ce qui est personnel vient d'un seul document, lu une seule fois.
        personne = load_profil()

        return cls(
            freshrss_base_url=base_url,
            freshrss_username=username,
            freshrss_api_password=api_password,
            output_dir=pathlib.Path(_env("RSSRESUME_OUTPUT_DIR") or "output"),
            categories=_split_csv(_env("RSSRESUME_CATEGORIES")),
            excluded_categories=_split_csv(_env("RSSRESUME_EXCLUDED_CATEGORIES")),
            summary_language=_env("RSSRESUME_SUMMARY_LANGUAGE", "fr") or "fr",
            timezone=load_timezone(_env(ENV_TIMEZONE)),
            profil=personne.texte,
            stack=personne.stack,
            prenom=personne.prenom,
            audio_mode=load_audio_mode(_env(ENV_AUDIO_MODE)),
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
            smtp_to=list(personne.emails),
            smtp_use_tls=(_env("SMTP_USE_TLS", "true") or "").lower() == "true",
            smtp_use_ssl=(_env("SMTP_USE_SSL", "false") or "").lower() == "true",
            mail_transport=load_mail_transport(_env(ENV_MAIL_TRANSPORT)),
            resend_api_key=_env(ENV_RESEND_API_KEY),
            certfr_categories=_split_categories(
                _env(ENV_CERTFR_CATEGORIES), ENV_CERTFR_CATEGORIES
            ),
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

    def est_deterministe(self, category: str) -> bool:
        """Vrai quand cette catégorie est routée hors du pipeline LLM.

        La comparaison retire la casse **et** les accents, là où `excluded_categories` ne
        replie que la casse. C'est délibéré et ce n'est pas une préférence : le libellé
        réel en porte — « 1 - Alertes et avis CERT-FR ANSSI » —, et un libellé recopié
        dans une variable d'environnement les perd régulièrement en route ; `.env.local`
        contient déjà un `RSSRESUME_CATEGORY_THRESHOLDS` écrit sans. Une catégorie qu'on
        croit routée et qui ne l'est pas ne fait pas d'erreur : elle repasse par le
        scoring, le résumé et la synthèse vocale, tous les matins, sans que rien ne le dise.
        """
        replie = casefold_ascii(category)
        return any(casefold_ascii(nom) == replie for nom in self.certfr_categories)
