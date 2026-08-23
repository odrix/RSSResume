"""Client de l'API Google Reader exposée par FreshRSS."""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

from rssresume import console
from rssresume.config import AppConfig
from rssresume.models import Article
from rssresume.text import strip_html

API_ROOT = "/api/greader.php"
LABEL_STREAM_PREFIX = "user/-/label/"
READ_STATE = "user/-/state/com.google/read"
PAGE_SIZE = "100"
#: Nombre maximum d'articles marqués comme lus par appel edit-tag.
EDIT_TAG_BATCH_SIZE = 100


class FreshRSSClient:
    def __init__(self, config: AppConfig):
        self._config = config
        self._auth_token: str | None = None
        self._edit_token: str | None = None

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
            self._build_url(f"{API_ROOT}/accounts/ClientLogin"),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).decode("utf-8", errors="replace")

        for line in body.splitlines():
            if line.startswith("Auth="):
                self._auth_token = line.split("=", 1)[1].strip()
                console.log(f"FreshRSS : authentifié en tant que {self._config.freshrss_username}")
                return self._auth_token
        raise RuntimeError("FreshRSS authentication succeeded without returning an Auth token.")

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"GoogleLogin auth={self._ensure_auth_token()}"}

    def _json_get(self, path: str, params: dict[str, str] | None = None) -> dict:
        body = self._request(self._build_url(path, params), headers=self._auth_headers())
        return json.loads(body.decode("utf-8"))

    def _post_form(self, path: str, fields: list[tuple[str, str]]) -> bytes:
        headers = self._auth_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self._request(self._build_url(path), data=urllib.parse.urlencode(fields).encode(), headers=headers)

    def _ensure_edit_token(self) -> str:
        """Jeton anti-CSRF exigé par FreshRSS pour toute écriture."""
        if self._edit_token:
            return self._edit_token
        body = self._request(self._build_url(f"{API_ROOT}/reader/api/0/token"), headers=self._auth_headers())
        self._edit_token = body.decode("utf-8", errors="replace").strip()
        if not self._edit_token:
            raise RuntimeError("FreshRSS returned an empty edit token.")
        return self._edit_token

    def list_categories(self) -> list[str]:
        payload = self._json_get(f"{API_ROOT}/reader/api/0/subscription/list", {"output": "json"})
        categories: set[str] = set()
        for subscription in payload.get("subscriptions", []):
            # Un flux sans catégorie renvoie une liste vide : il n'est jamais traité.
            for category in subscription.get("categories", []):
                stream_id = str(category.get("id") or "")
                if not stream_id.startswith(LABEL_STREAM_PREFIX):
                    # Flux d'état (reading-list, starred, ...) : hors catégorie utilisateur.
                    continue
                label = (category.get("label") or stream_id[len(LABEL_STREAM_PREFIX):]).strip()
                if label:
                    categories.add(label)
        console.log(f"FreshRSS : {len(categories)} catégorie(s) découverte(s)")
        return sorted(categories)

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        stream_id = urllib.parse.quote(f"{LABEL_STREAM_PREFIX}{category}", safe="")
        path = f"{API_ROOT}/reader/api/0/stream/contents/{stream_id}"
        items: list[Article] = []
        continuation: str | None = None

        while True:
            params = {"output": "json", "n": PAGE_SIZE}
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
                        item_id=str(item.get("id") or ""),
                        category=category,
                        title=item.get("title") or "Sans titre",
                        url=(item.get("alternate") or [{}])[0].get("href") or "",
                        published_at=published,
                        feed_title=item.get("origin", {}).get("title") or "",
                        content_text=strip_html(content),
                    )
                )

            continuation = payload.get("continuation")
            if not continuation:
                break

        return sorted(items, key=lambda article: article.published_at)

    def mark_as_read(self, articles: list[Article]) -> None:
        item_ids = [article.item_id for article in articles if article.item_id]
        if not item_ids:
            return

        token = self._ensure_edit_token()
        console.log(f"FreshRSS : marquage de {len(item_ids)} article(s) comme lus")
        for start in range(0, len(item_ids), EDIT_TAG_BATCH_SIZE):
            batch = item_ids[start:start + EDIT_TAG_BATCH_SIZE]
            fields = [("T", token), ("a", READ_STATE)] + [("i", item_id) for item_id in batch]
            self._post_form(f"{API_ROOT}/reader/api/0/edit-tag", fields)
