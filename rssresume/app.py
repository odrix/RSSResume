from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email.message
import html
import json
import mimetypes
import os
import pathlib
import re
import shutil
import smtplib
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, Protocol


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "category"


def _authorization_header(api_key: str) -> str:
    return "Bearer " + api_key


@dataclasses.dataclass(frozen=True)
class AppConfig:
    freshrss_base_url: str
    freshrss_username: str
    freshrss_api_password: str
    output_dir: pathlib.Path
    categories: list[str]
    summary_language: str
    summary_model: str | None
    tts_model: str | None
    tts_voice: str | None
    llm_base_url: str | None
    llm_api_key: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from: str | None
    smtp_to: list[str]
    smtp_use_tls: bool
    smtp_use_ssl: bool

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

        return cls(
            freshrss_base_url=base_url,
            freshrss_username=username,
            freshrss_api_password=api_password,
            output_dir=pathlib.Path(_env("RSSRESUME_OUTPUT_DIR", "output")),
            categories=_split_csv(_env("RSSRESUME_CATEGORIES")),
            summary_language=_env("RSSRESUME_SUMMARY_LANGUAGE", "fr") or "fr",
            summary_model=_env("OPENAI_SUMMARY_MODEL", "gpt-4o-mini"),
            tts_model=_env("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            tts_voice=_env("OPENAI_TTS_VOICE", "alloy"),
            llm_base_url=_env("OPENAI_BASE_URL"),
            llm_api_key=_env("OPENAI_API_KEY"),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=int(_env("SMTP_PORT", "587") or "587"),
            smtp_username=_env("SMTP_USERNAME"),
            smtp_password=_env("SMTP_PASSWORD"),
            smtp_from=_env("SMTP_FROM"),
            smtp_to=_split_csv(_env("SMTP_TO")),
            smtp_use_tls=(_env("SMTP_USE_TLS", "true") or "").lower() == "true",
            smtp_use_ssl=(_env("SMTP_USE_SSL", "false") or "").lower() == "true",
        )


@dataclasses.dataclass(frozen=True)
class Article:
    category: str
    title: str
    url: str
    published_at: dt.datetime
    feed_title: str
    content_text: str


@dataclasses.dataclass(frozen=True)
class CategoryDigest:
    category: str
    articles: list[Article]
    summary_text: str
    audio_path: pathlib.Path


class FreshRSSReader(Protocol):
    def list_categories(self) -> list[str]:
        ...

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        ...


class SummaryWriter(Protocol):
    def summarize(self, category: str, articles: list[Article]) -> str:
        ...


class AudioWriter(Protocol):
    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        ...


class MailSender(Protocol):
    def is_configured(self) -> bool:
        ...

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        ...


class FreshRSSClient:
    def __init__(self, config: AppConfig):
        self._config = config
        self._auth_token: str | None = None

    def _build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        base = self._config.freshrss_base_url.rstrip("/")
        url = f"{base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _request(self, url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FreshRSS request failed: {exc.code} {body}") from exc

    def _ensure_auth_token(self) -> str:
        if self._auth_token:
            return self._auth_token

        payload = urllib.parse.urlencode(
            {
                "Email": self._config.freshrss_username,
                "Passwd": self._config.freshrss_api_password,
            }
        ).encode()
        body = self._request(
            self._build_url("/api/greader.php/accounts/ClientLogin"),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).decode("utf-8", errors="replace")

        for line in body.splitlines():
            if line.startswith("Auth="):
                self._auth_token = line.split("=", 1)[1].strip()
                return self._auth_token
        raise RuntimeError("FreshRSS authentication succeeded without returning an Auth token.")

    def _json_get(self, path: str, params: dict[str, str] | None = None) -> dict:
        token = self._ensure_auth_token()
        body = self._request(
            self._build_url(path, params),
            headers={"Authorization": f"GoogleLogin auth={token}"},
        )
        return json.loads(body.decode("utf-8"))

    def list_categories(self) -> list[str]:
        payload = self._json_get("/api/greader.php/reader/api/0/subscription/list", {"output": "json"})
        categories: set[str] = set()
        for subscription in payload.get("subscriptions", []):
            for category in subscription.get("categories", []):
                label = category.get("label")
                if label:
                    categories.add(label)
        return sorted(categories)

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        stream_id = urllib.parse.quote(f"user/-/label/{category}", safe="")
        path = f"/api/greader.php/reader/api/0/stream/contents/{stream_id}"
        items: list[Article] = []
        continuation: str | None = None

        while True:
            params = {"output": "json", "n": "100"}
            if continuation:
                params["c"] = continuation
            payload = self._json_get(path, params)
            batch = payload.get("items", [])
            if not batch:
                break

            for item in batch:
                published = dt.datetime.fromtimestamp(item.get("published", 0), tz=dt.timezone.utc)
                if published < start:
                    continue
                if published >= end:
                    continue
                content = item.get("summary", {}).get("content") or item.get("content", {}).get("content") or ""
                items.append(
                    Article(
                        category=category,
                        title=item.get("title") or "Sans titre",
                        url=(item.get("alternate") or [{}])[0].get("href") or "",
                        published_at=published,
                        feed_title=item.get("origin", {}).get("title") or "",
                        content_text=_strip_html(content),
                    )
                )

            continuation = payload.get("continuation")
            if not continuation:
                break

        return sorted(items, key=lambda article: article.published_at)


class SummaryGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def summarize(self, category: str, articles: list[Article]) -> str:
        if not articles:
            return self._summarize_fallback(category, articles)
        if self._config.llm_api_key and self._config.llm_base_url:
            return self._summarize_with_openai(category, articles)
        return self._summarize_fallback(category, articles)

    def _summarize_with_openai(self, category: str, articles: list[Article]) -> str:
        prompt_articles = [
            {
                "title": article.title,
                "feed": article.feed_title,
                "url": article.url,
                "excerpt": article.content_text[:800],
            }
            for article in articles
        ]
        payload = {
            "model": self._config.summary_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu rédiges des résumés audio quotidiens de flux RSS. "
                        "Réponds dans une langue naturelle, concise, adaptée à une lecture vocale."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Résume les articles du jour pour la catégorie '{category}' en {self._config.summary_language}. "
                        "Fais un court paragraphe d'introduction, puis 3 à 6 points clés maximum, "
                        "et une phrase de conclusion.\n\n"
                        f"Articles:\n{json.dumps(prompt_articles, ensure_ascii=False)}"
                    ),
                },
            ],
        }
        return self._openai_json_request("/chat/completions", payload)["choices"][0]["message"]["content"].strip()

    def _openai_json_request(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self._config.llm_base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": _authorization_header(self._config.llm_api_key),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI-compatible summary request failed: {exc.code} {body}") from exc

    @staticmethod
    def _summarize_fallback(category: str, articles: list[Article]) -> str:
        if not articles:
            return f"Aucun nouvel article aujourd'hui dans la catégorie {category}."

        lines = [f"Résumé quotidien pour la catégorie {category}. {len(articles)} article(s) aujourd'hui."]
        for article in articles[:5]:
            excerpt = article.content_text[:180].rstrip()
            if excerpt:
                lines.append(f"- {article.title} ({article.feed_title}) : {excerpt}.")
            else:
                lines.append(f"- {article.title} ({article.feed_title}).")
        if len(articles) > 5:
            lines.append(f"- {len(articles) - 5} autre(s) article(s) complètent cette catégorie.")
        lines.append("Fin du résumé du jour.")
        return "\n".join(lines)


class AudioGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if shutil.which("espeak"):
            subprocess.run(["espeak", "--stdin", "-w", str(output_path)], input=text.encode("utf-8"), check=True)
            return output_path
        if self._config.llm_api_key and self._config.llm_base_url:
            request = urllib.request.Request(
                f"{self._config.llm_base_url.rstrip('/')}/audio/speech",
                data=json.dumps(
                    {
                        "model": self._config.tts_model,
                        "voice": self._config.tts_voice,
                        "input": text,
                        "format": output_path.suffix.lstrip(".") or "mp3",
                    }
                ).encode(),
                headers={
                    "Authorization": _authorization_header(self._config.llm_api_key),
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request) as response:
                    output_path.write_bytes(response.read())
                    return output_path
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"OpenAI-compatible audio request failed: {exc.code} {body}") from exc
        raise RuntimeError("No text-to-speech backend available. Install espeak or configure OPENAI_BASE_URL and OPENAI_API_KEY.")


class EmailSender:
    def __init__(self, config: AppConfig):
        self._config = config

    def is_configured(self) -> bool:
        return bool(self._config.smtp_host and self._config.smtp_from and self._config.smtp_to)

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        if not self.is_configured():
            raise RuntimeError("SMTP configuration is incomplete.")

        message = email.message.EmailMessage()
        message["Subject"] = subject
        message["From"] = self._config.smtp_from
        message["To"] = ", ".join(self._config.smtp_to)
        message.set_content(body)

        for attachment in attachments:
            mime_type, _ = mimetypes.guess_type(str(attachment))
            maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
            message.add_attachment(
                attachment.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment.name,
            )

        if self._config.smtp_use_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port)
        else:
            smtp = smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)

        with smtp:
            if self._config.smtp_use_tls and not self._config.smtp_use_ssl:
                smtp.starttls()
            if self._config.smtp_username and self._config.smtp_password:
                smtp.login(self._config.smtp_username, self._config.smtp_password)
            smtp.send_message(message)


class DigestService:
    def __init__(
        self,
        config: AppConfig,
        freshrss_client: FreshRSSReader,
        summary_generator: SummaryWriter,
        audio_generator: AudioWriter,
        email_sender: MailSender,
    ):
        self._config = config
        self._freshrss_client = freshrss_client
        self._summary_generator = summary_generator
        self._audio_generator = audio_generator
        self._email_sender = email_sender

    def run(self, day: dt.date, send_email: bool = True) -> list[CategoryDigest]:
        categories = self._config.categories or self._freshrss_client.list_categories()
        digests: list[CategoryDigest] = []

        for category in categories:
            articles = self._freshrss_client.fetch_daily_articles(category, day)
            summary_text = self._summary_generator.summarize(category, articles)
            extension = ".wav" if shutil.which("espeak") else ".mp3"
            audio_path = self._config.output_dir / day.isoformat() / f"{_slugify(category)}{extension}"
            audio_path = self._audio_generator.synthesize(summary_text, audio_path)
            digests.append(CategoryDigest(category=category, articles=articles, summary_text=summary_text, audio_path=audio_path))

        if send_email and self._email_sender.is_configured():
            body = "\n\n".join(digest.summary_text for digest in digests) or f"Aucun article trouvé pour le {day.isoformat()}."
            self._email_sender.send(
                subject=f"Résumé RSS du {day.isoformat()}",
                body=body,
                attachments=[digest.audio_path for digest in digests],
            )
        return digests


def build_service(config: AppConfig) -> DigestService:
    return DigestService(
        config=config,
        freshrss_client=FreshRSSClient(config),
        summary_generator=SummaryGenerator(config),
        audio_generator=AudioGenerator(config),
        email_sender=EmailSender(config),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily FreshRSS audio summaries by category.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Date to summarize (YYYY-MM-DD).")
    parser.add_argument("--dry-run", action="store_true", help="Generate summaries and audio without sending email.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = AppConfig.from_env()
    service = build_service(config)
    day = dt.date.fromisoformat(args.date)
    digests = service.run(day, send_email=not args.dry_run)
    print(f"Generated {len(digests)} category digest(s) for {day.isoformat()} in {config.output_dir}.")
    return 0
