"""Doublures et fabriques partagées par les tests."""

import pathlib

from rssresume import console
from rssresume.config import AppConfig

# Les tests n'affichent pas le suivi d'exécution.
console.enable(False)


class FakeFreshRSSClient:
    def __init__(self, articles_by_category):
        self._articles_by_category = articles_by_category
        self.marked_as_read = []

    def list_categories(self):
        return list(self._articles_by_category)

    def fetch_daily_articles(self, category, day):
        return self._articles_by_category[category]

    def mark_as_read(self, articles):
        self.marked_as_read.extend(articles)


class FakeAudioGenerator:
    def synthesize(self, text, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return output_path


class FakeEmailSender:
    def __init__(self):
        self.messages = []

    def is_configured(self):
        return True

    def send(self, subject, body, attachments):
        self.messages.append((subject, body, list(attachments)))


def make_config(output_dir):
    return AppConfig(
        freshrss_base_url="https://example.com",
        freshrss_username="user",
        freshrss_api_password="password",
        output_dir=pathlib.Path(output_dir),
        categories=["Tech", "News"],
        excluded_categories=[],
        summary_language="fr",
        summary_model=None,
        tts_model=None,
        tts_voice=None,
        llm_base_url=None,
        llm_api_key=None,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-pass",
        smtp_from="from@example.com",
        smtp_to=["to@example.com"],
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
