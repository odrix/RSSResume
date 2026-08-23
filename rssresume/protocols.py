"""Contrats implémentés par les collaborateurs de DigestService."""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Iterable, Protocol

from rssresume.models import Article


class FreshRSSClientProtocol(Protocol):
    def list_categories(self) -> list[str]:
        ...

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        ...

    def mark_as_read(self, articles: list[Article]) -> None:
        ...


class SummaryGeneratorProtocol(Protocol):
    def summarize(self, category: str, articles: list[Article]) -> str:
        ...


class AudioGeneratorProtocol(Protocol):
    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        ...


class EmailSenderProtocol(Protocol):
    def is_configured(self) -> bool:
        ...

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        ...
