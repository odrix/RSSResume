"""Client de l'API Google Reader exposée par FreshRSS."""

from __future__ import annotations

import datetime as dt
import json
import re
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
#: Nombre maximum d'articles modifiés par appel edit-tag.
EDIT_TAG_BATCH_SIZE = 100
#: Actions edit-tag : ajouter ou retirer un flux d'état ou un label.
TAG_ADD = "a"
TAG_REMOVE = "r"

#: Tag posé sur chaque article noté. Le zéro initial garde l'ordre alphabétique
#: cohérent avec l'ordre numérique dans la liste des tags FreshRSS.
SCORE_TAG_TEMPLATE = "score-{score:02d}"
#: Tag posé sur les articles retenus pour le digest du jour.
DIGEST_TAG = "digested"
#: Tag mémorisant le prompt qui a produit le score, pour ne renoter qu'après l'avoir changé.
SCORING_TAG_TEMPLATE = "scoring-{digest}"

SCORE_TAG_PATTERN = re.compile(r"^score-(\d{2})$")
SCORING_TAG_PATTERN = re.compile(r"^scoring-([0-9a-f]+)$")


def score_tag(score: int) -> str:
    return SCORE_TAG_TEMPLATE.format(score=score)


def scoring_tag(digest: str) -> str:
    return SCORING_TAG_TEMPLATE.format(digest=digest)


def user_labels(categories: list) -> tuple[str, ...]:
    """Tags utilisateur d'un article ; les flux d'état (read, starred) sont ignorés."""
    return tuple(
        str(entry)[len(LABEL_STREAM_PREFIX):]
        for entry in categories
        if str(entry).startswith(LABEL_STREAM_PREFIX)
    )


def score_from_tags(tags: tuple[str, ...]) -> int | None:
    """Score déjà posé sur l'article, relu depuis ses tags."""
    for tag in tags:
        match = SCORE_TAG_PATTERN.match(tag)
        if match:
            return int(match.group(1))
    return None


def scoring_digest_from_tags(tags: tuple[str, ...]) -> str | None:
    """Empreinte du prompt ayant produit le score de l'article."""
    for tag in tags:
        match = SCORING_TAG_PATTERN.match(tag)
        if match:
            return match.group(1)
    return None


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
                        tags=user_labels(item.get("categories", [])),
                    )
                )

            continuation = payload.get("continuation")
            if not continuation:
                break

        return sorted(items, key=lambda article: article.published_at)

    def _edit_tag(self, item_ids: list[str], stream_id: str, action: str = TAG_ADD) -> None:
        """Ajoute ou retire un flux d'état ou un label sur des articles, par lots."""
        retenus = [item_id for item_id in item_ids if item_id]
        if not retenus:
            return

        token = self._ensure_edit_token()
        for start in range(0, len(retenus), EDIT_TAG_BATCH_SIZE):
            batch = retenus[start:start + EDIT_TAG_BATCH_SIZE]
            fields = [("T", token), (action, stream_id)] + [("i", item_id) for item_id in batch]
            self._post_form(f"{API_ROOT}/reader/api/0/edit-tag", fields)

    def mark_as_read(self, articles: list[Article]) -> None:
        item_ids = [article.item_id for article in articles if article.item_id]
        if not item_ids:
            return

        console.log(f"FreshRSS : marquage de {len(item_ids)} article(s) comme lus")
        self._edit_tag(item_ids, READ_STATE)

    def add_label(self, item_ids: list[str], label: str) -> None:
        """Pose un tag utilisateur sur des articles. Reposer un tag existant est sans effet."""
        self._edit_tag(item_ids, f"{LABEL_STREAM_PREFIX}{label}")

    def tag_scores(self, scores: dict[str, int], scoring_digest: str | None = None) -> None:
        """Pose un tag `score-NN` par article, un appel par valeur de score distincte.

        Prend un dict {item_id: score}. `scoring_digest` ajoute l'empreinte du prompt,
        qui sert de cache : un article la portant déjà n'a pas besoin d'être renoté.
        """
        par_score: dict[int, list[str]] = {}
        for item_id, score in scores.items():
            if item_id:
                par_score.setdefault(int(score), []).append(item_id)
        if not par_score:
            return

        console.log(
            f"FreshRSS : notation de {sum(len(ids) for ids in par_score.values())} article(s) "
            f"sur {len(par_score)} valeur(s) de score"
        )
        for score in sorted(par_score):
            self.add_label(par_score[score], score_tag(score))
        if scoring_digest:
            self.add_label([item_id for ids in par_score.values() for item_id in ids],
                           scoring_tag(scoring_digest))

    def remove_label(self, item_ids: list[str], label: str) -> None:
        """Retire un tag utilisateur des articles."""
        self._edit_tag(item_ids, f"{LABEL_STREAM_PREFIX}{label}", TAG_REMOVE)

    def clear_scoring_tags(self, articles: list[Article]) -> None:
        """Retire score et empreinte des articles notés par un prompt devenu obsolète.

        Ne balaie que les tags réellement portés par les articles : un article renoté
        ne garde jamais l'empreinte ni le score de la version précédente du prompt.
        """
        par_label: dict[str, list[str]] = {}
        for article in articles:
            if not article.item_id:
                continue
            for tag in article.tags:
                if SCORE_TAG_PATTERN.match(tag) or SCORING_TAG_PATTERN.match(tag):
                    par_label.setdefault(tag, []).append(article.item_id)
        if not par_label:
            return

        console.log(f"FreshRSS : nettoyage de {len(par_label)} tag(s) de scoring obsolète(s)")
        for label, item_ids in sorted(par_label.items()):
            self.remove_label(item_ids, label)

    def mark_digested(self, item_ids: list[str]) -> None:
        """Pose le tag du digest sur les articles retenus pour la synthèse du jour."""
        retenus = [item_id for item_id in item_ids if item_id]
        if not retenus:
            return

        console.log(f"FreshRSS : tag '{DIGEST_TAG}' sur {len(retenus)} article(s)")
        self.add_label(retenus, DIGEST_TAG)
