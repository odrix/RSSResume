"""Contrats implémentés par les collaborateurs de DigestService."""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Iterable, Protocol

from rssresume.models import Article, Note


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


class EmailSenderProtocol(Protocol):
    def is_configured(self) -> bool:
        ...

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        ...
