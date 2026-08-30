"""Contrats implémentés par les collaborateurs de DigestService."""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Iterable, Protocol

from rssresume.certfr import Revue, Stack
from rssresume.models import Article, Ephemeride, Note


class FreshRSSClientProtocol(Protocol):
    def list_categories(self) -> list[str]:
        ...

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        ...

    def mark_as_read(self, articles: list[Article]) -> None:
        ...

    def mark_digested(self, item_ids: list[str]) -> None:
        ...

    def tag_notes(self, notes: dict[str, Note], scoring_digest: str | None = None) -> None:
        ...

    def clear_scoring_tags(self, articles: list[Article]) -> None:
        ...


class ScorerProtocol(Protocol):
    """Ce que `DigestService` attend d'un noteur : un `LLMProvider`, ou une doublure."""

    def score_articles(self, articles: list[dict], profil: str | None = None) -> list[dict]:
        ...

    def scoring_fingerprint(self, profil: str | None = None) -> str:
        ...


class SummaryGeneratorProtocol(Protocol):
    def summarize(
        self, category: str, articles: list[Article], notes: dict[str, Note] | None = None
    ) -> str:
        ...


class AudioGeneratorProtocol(Protocol):
    #: Extension du fichier écrit, imposée par le moteur de synthèse.
    @property
    def extension(self) -> str:
        ...

    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        ...


class EphemerideServiceProtocol(Protocol):
    """Ce que `DigestService` attend de l'éphéméride : une phrase pour cette date.

    Jamais `None` : le service sait toujours quoi rendre, quitte à descendre sur le
    calendrier. L'introduction de l'email n'a donc pas de cas « pas d'éphéméride » à
    traiter, ce qui est exactement la raison d'être du repli.
    """

    def of(self, day: dt.date) -> Ephemeride:
        ...


class CertfrServiceProtocol(Protocol):
    """Ce que `DigestService` attend du traitement déterministe des avis CERT-FR.

    Deux choses seulement, et la seconde n'est pas décorative : la journée triée, et la
    liste contre laquelle elle l'a été. C'est cette liste que le journal de la catégorie
    fixe, à la place de l'empreinte de scoring — qui n'a ici aucun sens, puisque aucun
    prompt n'a servi.
    """

    @property
    def stack(self) -> Stack:
        ...

    def lire(self, articles: list[Article]) -> Revue:
        ...


class EmailSenderProtocol(Protocol):
    def is_configured(self) -> bool:
        ...

    def send(
        self,
        subject: str,
        body: str,
        attachments: Iterable[pathlib.Path],
        html: str | None = None,
    ) -> None:
        """Envoie le message. `body` est le texte, `html` la version mise en page.

        Les deux, et pas l'un ou l'autre : le HTML porte la mise en page, le texte reste
        la seule version qu'un client en texte seul saura afficher. Un `html` à `None`
        envoie un message de texte pur, comme avant.
        """
        ...
