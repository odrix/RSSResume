"""Doublures et fabriques partagées par les tests."""

import pathlib

from rssresume import console
from rssresume.config import AppConfig
from rssresume.profil import DEFAULT_PROFIL

# Les tests n'affichent pas le suivi d'exécution.
console.enable(False)


class FakeFreshRSSClient:
    def __init__(self, articles_by_category):
        self._articles_by_category = articles_by_category
        self.marked_as_read = []
        self.digested = []
        self.scored = {}
        self.themed = {}
        self.scoring_digest = None
        self.cleared = []

    def list_categories(self):
        return list(self._articles_by_category)

    def fetch_daily_articles(self, category, day):
        return self._articles_by_category[category]

    def mark_as_read(self, articles):
        self.marked_as_read.extend(articles)

    def mark_digested(self, item_ids):
        self.digested.extend(item_ids)

    def tag_notes(self, notes, scoring_digest=None):
        # Les deux tags sont relevés séparément : les tests s'intéressent surtout aux scores.
        self.scored.update({item_id: note.score for item_id, note in notes.items()})
        self.themed.update({item_id: note.thematique for item_id, note in notes.items()})
        self.scoring_digest = scoring_digest

    def clear_scoring_tags(self, articles):
        self.cleared.extend(article.item_id for article in articles)


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
        # Le profil par défaut, pour que l'empreinte de scoring des tests soit celle
        # que `scoring_prompt_digest()` calcule sans argument.
        profil=DEFAULT_PROFIL,
        score_threshold=7,
        max_digest_items=12,
        summary_model=None,
        tts_model=None,
        tts_voice=None,
        tts_instructions=None,
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
