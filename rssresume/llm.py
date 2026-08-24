"""Adaptateur vers une API compatible OpenAI.

Tout ce qui est propre au fournisseur vit ici : forme des requêtes, noms des
paramètres, réglages par type d'appel, extraction des réponses. Les appelants
n'échangent que du texte et des octets — basculer sur un autre fournisseur ne
demandera de réécrire que ce module.
"""

from __future__ import annotations

import dataclasses
import json
import os
import urllib.error
import urllib.request

PROVIDER = "OpenAI-compatible"
CHAT_PATH = "/chat/completions"
SPEECH_PATH = "/audio/speech"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class LLMError(RuntimeError):
    """Échec côté fournisseur : identifiants absents, requête rejetée, réponse tronquée."""


@dataclasses.dataclass(frozen=True)
class ChatProfile:
    """Réglages d'un type d'appel.

    `model` est le défaut du type d'appel, que l'appelant peut surcharger.
    `max_tokens` à None laisse le plafond par défaut du fournisseur.
    """

    label: str
    model: str
    temperature: float
    max_tokens: int | None = None


#: Notation d'articles : la reproductibilité prime, le seuil de sélection en dépend.
#: 4096 tokens couvrent un lot de 40 articles (~60 tokens chacun).
SCORING = ChatProfile(
    "scoring",
    model=os.getenv("OPENAI_SCORING_MODEL", "gpt-4o-mini"),
    temperature=0.1,
    max_tokens=4096,
)

#: Résumé d'un article : factuel avant tout, la marge de style n'apporte rien
#: et la dérive factuelle coûte cher sur des CVE ou des échéances réglementaires.
ARTICLE_SUMMARY = ChatProfile(
    "article summary",
    model=os.getenv("OPENAI_ARTICLE_MODEL", "gpt-4o"),
    temperature=0.3,
    max_tokens=512,
)

#: Digest audio d'une catégorie : un peu de liberté de formulation pour l'oral.
#: Sans réglage explicite, ce type d'appel tournait à la valeur par défaut, 1.0.
DIGEST = ChatProfile(
    "digest",
    model=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini"),
    temperature=0.4,
)


def credentials_from_env() -> tuple[str, str]:
    """Base URL et clé d'API lues dans l'environnement, pour les appelants sans AppConfig."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise LLMError("OPENAI_API_KEY n'est pas définie dans l'environnement.")
    return (os.getenv("OPENAI_BASE_URL") or "").strip() or DEFAULT_BASE_URL, api_key


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
        raise LLMError(f"{PROVIDER} {error_label} request failed: {exc.code} {body}") from exc


def post_json(base_url: str, api_key: str, path: str, payload: dict, error_label: str) -> dict:
    """POST JSON et décode la réponse JSON."""
    return json.loads(post(base_url, api_key, path, payload, error_label).decode("utf-8"))


def chat(
    base_url: str,
    api_key: str,
    profile: ChatProfile,
    system: str,
    user: str,
    model: str | None = None,
) -> str:
    """Un aller-retour de complétion ; renvoie le texte de la réponse.

    `model` surcharge celui du profil, pour les appelants qui le tiennent de leur config.

    `max_tokens` est le paramètre historique : il vaut pour la famille gpt-4o,
    mais les modèles de raisonnement (série o) attendent `max_completion_tokens`.
    """
    model = model or profile.model
    payload: dict = {
        "model": model,
        "temperature": profile.temperature,
        # Un `seed` ici rendrait les réponses reproductibles au mieux des efforts
        # du fournisseur ; la température seule n'y suffit pas.
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if profile.max_tokens is not None:
        payload["max_tokens"] = profile.max_tokens

    choice = post_json(base_url, api_key, CHAT_PATH, payload, profile.label)["choices"][0]
    if choice.get("finish_reason") == "length":
        # Sans ce garde-fou, une réponse coupée ressort en erreur de parsing bien plus loin.
        raise LLMError(
            f"{PROVIDER} {profile.label}: réponse tronquée par "
            f"max_tokens ({profile.max_tokens}) sur le modèle {model}."
        )
    return (choice["message"]["content"] or "").strip()


def speak(
    base_url: str,
    api_key: str,
    model: str,
    voice: str,
    text: str,
    audio_format: str,
) -> bytes:
    """Synthèse vocale ; renvoie les octets audio."""
    payload = {"model": model, "voice": voice, "input": text, "format": audio_format}
    return post(base_url, api_key, SPEECH_PATH, payload, "tts")
