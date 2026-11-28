"""Client de l'API Google Reader exposée par FreshRSS."""

from __future__ import annotations

import copy
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

from rssresume.config import AppConfig
from rssresume.models import Article
from rssresume.tools import console, http
from rssresume.tools.text import strip_html

API_ROOT = "/api/greader.php"
LABEL_STREAM_PREFIX = "user/-/label/"
READ_STATE = "user/-/state/com.google/read"
PAGE_SIZE = "100"
#: Nombre maximum d'articles modifiés par appel edit-tag.
EDIT_TAG_BATCH_SIZE = 100
#: Actions edit-tag : ajouter ou retirer un flux d'état ou un label.
TAG_ADD = "a"
TAG_REMOVE = "r"

#: Tag posé sur les articles retenus pour le digest du jour. Le seul tag que le
#: pipeline pose encore : le cache de scoring vit dans la base SQLite, plus ici.
DIGEST_TAG = "digested"



def _endpoint(url: str) -> str:
    """Le chemin appelé, sans l'hôte ni les paramètres : de quoi lire une trace de reprise."""
    return urllib.parse.urlsplit(url).path or url


class Etiquettes:
    """Les tags d'une personne : le préfixe sous lequel elle pose le sien.

    Le cache de scoring (`score-NN`, `theme-<x>`, `scoring-<hash>`) a quitté FreshRSS
    pour la base SQLite : le nom de la personne ne préfixe plus que `digested`, le
    seul tag que le pipeline pose encore. Un label FreshRSS accepte le tiret, et un
    nom de profil ne porte ni espace ni majuscule.

    Sans nom, la configuration de l'installation, celle des tests, aucun préfixe.
    """

    def __init__(self, username: str = ""):
        self.prefixe = f"{username}-" if username else ""

    @property
    def digest(self) -> str:
        return self.prefixe + DIGEST_TAG


def user_labels(categories: list) -> tuple[str, ...]:
    """Tags utilisateur d'un article ; les flux d'état (read, starred) sont ignorés."""
    return tuple(
        str(entry)[len(LABEL_STREAM_PREFIX):]
        for entry in categories
        if str(entry).startswith(LABEL_STREAM_PREFIX)
    )


class _Session:
    """Ce que les clients d'une même tournée partagent : jetons et lectures déjà faites.

    Les personnes d'une tournée lisent les mêmes catégories du même jour. Les relire
    pour chacune ne changerait rien au résultat, les tags d'une autre personne ne
    les concernent pas, et multiplierait les appels par le nombre de profils.
    """

    def __init__(self):
        self.auth_token: str | None = None
        self.edit_token: str | None = None
        self.categories: list[str] | None = None
        self.journees: dict[tuple[str, dt.date], list[Article]] = {}


class FreshRSSClient:
    def __init__(self, config: AppConfig, include_read: bool = False):
        self._config = config
        #: Par défaut, les articles déjà lus sont écartés côté serveur : le pipeline
        #: marque comme lu ce qu'il a traité, donc un article lu est un article déjà
        #: digéré. Rejouer une journée close, elle, demande de les redemander.
        self._include_read = include_read
        self._session = _Session()
        #: Les tags de la personne servie, d'après la configuration : sans nom, aucun préfixe.
        self.etiquettes = Etiquettes(config.username)

    def pour(self, username: str) -> "FreshRSSClient":
        """Le même client, qui tague au nom de `username`, session et lectures partagées."""
        copie = copy.copy(self)
        copie.etiquettes = Etiquettes(username)
        return copie

    def _build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        base = self._config.freshrss_base_url.rstrip("/")
        url = f"{base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _request(self, url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        """Un aller-retour avec FreshRSS, rejoué tant que l'échec est passager.

        Le digest tourne la nuit : un 502 du reverse proxy pendant sa rotation de
        certificat suffisait à ce qu'aucune catégorie n'existe le lendemain matin.
        """
        request = urllib.request.Request(url, data=data, headers=headers or {})

        def _envoyer() -> bytes:
            with urllib.request.urlopen(request) as response:
                return response.read()

        try:
            return http.retry(_envoyer, f"FreshRSS {_endpoint(url)}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FreshRSS request failed: {exc.code} {body}") from exc

    def _ensure_auth_token(self) -> str:
        if self._session.auth_token:
            return self._session.auth_token

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
                self._session.auth_token = line.split("=", 1)[1].strip()
                console.log(f"FreshRSS : authentifié en tant que {self._config.freshrss_username}")
                return self._session.auth_token
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
        if self._session.edit_token:
            return self._session.edit_token
        body = self._request(self._build_url(f"{API_ROOT}/reader/api/0/token"), headers=self._auth_headers())
        self._session.edit_token = body.decode("utf-8", errors="replace").strip()
        if not self._session.edit_token:
            raise RuntimeError("FreshRSS returned an empty edit token.")
        return self._session.edit_token

    def list_categories(self) -> list[str]:
        """Les catégories, lues une fois par session : une par tournée, pas par profil."""
        if self._session.categories is None:
            self._session.categories = self._lire_categories()
        return list(self._session.categories)

    def fetch_daily_articles(self, category: str, day: dt.date) -> list[Article]:
        """Les articles du jour d'une catégorie, lus une fois par session.

        Rendre la même lecture à chaque profil n'est juste que parce que le marquage
        comme lu attend la fin de la tournée : aucun profil ne retire d'articles à ceux
        qui le suivent.
        """
        cle = (category, day)
        if cle not in self._session.journees:
            self._session.journees[cle] = self._lire_journee(category, day)
        return list(self._session.journees[cle])

    def _lire_categories(self) -> list[str]:
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

    def _lire_journee(self, category: str, day: dt.date) -> list[Article]:
        """Les articles du jour d'une catégorie, filtrés par l'API autant qu'elle le permet.

        La journée était découpée en Python *après* avoir paginé tout le flux : des dizaines
        d'appels par catégorie pour en garder vingt. L'API Google Reader sait le faire en
        base, `ot` borne la journée par le bas, `xt` écarte un flux d'état, ici les articles
        déjà lus.

        Le filtre Python reste derrière, en filet : il tient la borne haute, qui n'a pas de
        paramètre équivalent, et il couvre le cas d'un serveur qui ignorerait `ot`. Un
        paramètre inconnu est ignoré sans erreur : au pire on repaie la pagination d'avant,
        jamais un article manquant.

        La journée est celle du fuseau configuré, pas celle d'UTC : en heure d'été, un
        article publié à 1 h du matin à Paris tombait dans la veille et n'apparaissait
        donc dans aucun digest, la veille étant déjà livrée et ses articles marqués lus.
        Les horodatages restent comparés en absolu, seules les bornes changent d'origine.
        """
        start = dt.datetime.combine(day, dt.time.min, tzinfo=self._config.timezone)
        # Un jour civil, pas 24 heures : la nuit du changement d'heure en fait 23 ou 25.
        end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min,
                                  tzinfo=self._config.timezone)
        stream_id = urllib.parse.quote(f"{LABEL_STREAM_PREFIX}{category}", safe="")
        path = f"{API_ROOT}/reader/api/0/stream/contents/{stream_id}"
        filtres = {"output": "json", "n": PAGE_SIZE, "ot": str(int(start.timestamp()))}
        if not self._include_read:
            filtres["xt"] = READ_STATE
        items: list[Article] = []
        continuation: str | None = None

        while True:
            # Les filtres repartent à chaque page : la continuation dit où reprendre,
            # pas ce qu'on demandait.
            params = dict(filtres)
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

    def mark_digested(self, item_ids: list[str]) -> None:
        """Pose le tag du digest sur les articles retenus pour la synthèse du jour."""
        retenus = [item_id for item_id in item_ids if item_id]
        if not retenus:
            return

        console.log(f"FreshRSS : tag '{self.etiquettes.digest}' sur {len(retenus)} article(s)")
        self.add_label(retenus, self.etiquettes.digest)
