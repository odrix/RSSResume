"""Transport HTTP vers une API compatible OpenAI (résumés et synthèse vocale)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def authorization_header(api_key: str) -> str:
    return "Bearer " + api_key


def post(base_url: str, api_key: str, path: str, payload: dict, error_label: str) -> bytes:
    """POST JSON et renvoie le corps brut de la réponse."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": authorization_header(api_key),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{error_label} request failed: {exc.code} {body}") from exc


def post_json(base_url: str, api_key: str, path: str, payload: dict, error_label: str) -> dict:
    """POST JSON et décode la réponse JSON."""
    return json.loads(post(base_url, api_key, path, payload, error_label).decode("utf-8"))
