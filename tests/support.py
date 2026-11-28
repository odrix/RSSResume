"""Doublures et fabriques partagées par les tests."""

import pathlib
import zoneinfo
from unittest import mock

from rssresume.llm import processing
from rssresume.models import Note
from rssresume.tools import console
from rssresume.config import DEFAULT_ARTICLE_CHAR_LIMIT, AppConfig
from rssresume.profil import DEFAULT_PROFIL

# Les tests n'affichent pas le suivi d'exécution.
console.enable(False)

#: Modèle de notation des doublures. Fixé ici et non lu dans `providers.json` : les
#: tests vérifient la mécanique du cache d'empreintes, pas le modèle du jour.
SCORING_MODEL = "modele-de-test"


def empreinte(profil=None, axes=None):
    """L'empreinte que `FakeScorer` produit, pour comparer le cache des tests."""
    return processing.scoring_fingerprint(profil, SCORING_MODEL, axes)


class FakeFreshRSSClient:
    """Le client FreshRSS des tests : plus aucun tag de scoring n'y est posé,
    seul `digested` reste, le cache de scoring étant passé en base SQLite."""

    def __init__(self, articles_by_category):
        self._articles_by_category = articles_by_category
        self.marked_as_read = []
        self.digested = []

    def list_categories(self):
        return list(self._articles_by_category)

    def fetch_daily_articles(self, category, day):
        return self._articles_by_category[category]

    def mark_as_read(self, articles):
        self.marked_as_read.extend(articles)

    def mark_digested(self, item_ids):
        self.digested.extend(item_ids)


class FakeCacheScoring:
    """Cache de scoring en mémoire, même contrat que `CacheScoringSqlite`.

    Les notes sont rangées par (item_id, empreinte) ; `enregistrements` garde
    l'ordre des écritures pour les assertions.
    """

    def __init__(self):
        self._notes: dict[tuple[str, str], Note] = {}
        self.enregistrements: list[tuple[str, str, Note]] = []

    def note(self, item_id, empreinte):
        return self._notes.get((item_id, empreinte))

    def enregistrer(self, item_id, empreinte, note):
        self._notes[(item_id, empreinte)] = note
        self.enregistrements.append((item_id, empreinte, note))


class FakeScorer:
    """Un noteur qui ne parle à personne : il rend ce qu'on lui a dit de rendre.

    Même contrat qu'un `LLMProvider` côté notation, ce qui suffit à `DigestService`.
    """

    def __init__(self, notes=None, side_effect=None):
        # `score_articles` est un Mock : les tests l'interrogent comme n'importe quel
        # appel simulé (`assert_called_once`, `call_args`).
        self.score_articles = mock.Mock(
            return_value=[] if notes is None else notes, side_effect=side_effect
        )

    def scoring_fingerprint(self, profil=None, axes=None):
        return empreinte(profil, axes)


class FakeAudioGenerator:
    extension = ".wav"

    def synthesize(self, text, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return output_path


class FakeEmailSender:
    """Retient ce qu'on lui a demandé d'envoyer, les deux rendus compris.

    Le HTML est rangé en quatrième position et non à la place du texte : les tests qui
    lisent `messages[0][1]` jugent la version texte, qui reste celle que tout client
    sait afficher.
    """

    def __init__(self):
        self.messages = []
        #: L'URL de désabonnement de chaque envoi, à part pour ne pas changer la forme
        #: des messages que les tests existants relisent.
        self.desabonnements = []

    def is_configured(self):
        return True

    def send(self, subject, body, attachments, html=None, desabonnement=None):
        self.messages.append((subject, body, list(attachments), html))
        self.desabonnements.append(desabonnement)


def make_config(output_dir):
    return AppConfig(
        freshrss_base_url="https://example.com",
        freshrss_username="user",
        freshrss_api_password="password",
        output_dir=pathlib.Path(output_dir),
        categories=["Tech", "News"],
        excluded_categories=[],
        summary_language="fr",
        # Le fuseau des journées : les tests le fixent plutôt que de le lire de
        # l'environnement, sans quoi une machine en UTC ne verrait pas les mêmes bornes.
        timezone=zoneinfo.ZoneInfo("Europe/Paris"),
        # Le profil par défaut, pour que l'empreinte de scoring des tests soit celle
        # que `empreinte()` calcule sans argument.
        profil=DEFAULT_PROFIL,
        score_threshold=7,
        category_thresholds={},
        fallback_threshold=5,
        # Repli désactivé par défaut : chaque test qui l'attend le rallume, les autres
        # jugent la règle de base sans qu'un seuil se dérobe sous eux.
        min_digest_items=0,
        max_digest_items=12,
        article_char_limit=DEFAULT_ARTICLE_CHAR_LIMIT,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-pass",
        smtp_from="from@example.com",
        smtp_to=["to@example.com"],
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
