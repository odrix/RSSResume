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

from rssresume import runlog

PROVIDER = "OpenAI-compatible"
CHAT_PATH = "/chat/completions"
SPEECH_PATH = "/audio/speech"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class LLMError(RuntimeError):
    """Échec côté fournisseur : identifiants absents, requête rejetée, réponse tronquée."""


#: Familles de modèles raisonnants. Elles rejettent `temperature` et `max_tokens` en 400,
#: et attendent `reasoning_effort` et `max_completion_tokens` à la place. Le test porte sur
#: le modèle **effectif** et non sur le profil : le modèle est surchargeable par la
#: configuration, et les deux familles cohabitent dans une même exécution.
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def is_reasoning_model(model: str) -> bool:
    return (model or "").strip().lower().startswith(REASONING_PREFIXES)


@dataclasses.dataclass(frozen=True)
class ChatProfile:
    """Réglages d'un type d'appel, dans les deux familles de modèles.

    `model` est le défaut du type d'appel, que l'appelant peut surcharger.
    `temperature`/`max_tokens` valent pour les modèles classiques, `effort` et
    `reasoning_max_tokens` pour les raisonnants. Un plafond à None laisse celui du
    fournisseur.
    """

    label: str
    model: str
    temperature: float
    max_tokens: int | None = None
    #: Plafond distinct pour les modèles raisonnants : leur budget de sortie inclut les
    #: tokens de raisonnement, absents de la réponse. Réutiliser `max_tokens` tel quel
    #: ferait tronquer la réponse avant le premier mot écrit.
    reasoning_max_tokens: int | None = None
    #: Le bouton de réglage des modèles raisonnants, à la place de la température :
    #: none, low, medium, high, xhigh, max. Les tokens de raisonnement sont facturés
    #: en sortie, ce qui rend `none` et `low` économiquement significatifs.
    effort: str = "low"


#: Notation d'articles : la reproductibilité prime, le seuil de sélection en dépend.
#: Reste sur un modèle classique — la notation ne demande pas de raisonnement, et changer
#: son modèle change l'empreinte du prompt, donc renote tout l'historique.
#: 4096 tokens couvrent un lot de 40 articles (~60 tokens chacun).
SCORING = ChatProfile(
    "scoring",
    model=os.getenv("OPENAI_SCORING_MODEL", "gpt-4o-mini"),
    temperature=0.1,
    max_tokens=4096,
    # Si la notation passait un jour sur un modèle raisonnant : pas de raisonnement,
    # c'est un tri sur barème, et la régularité prime.
    reasoning_max_tokens=8192,
    effort="none",
)

#: Résumé d'un article : factuel avant tout, la marge de style n'apporte rien
#: et la dérive factuelle coûte cher sur des CVE ou des échéances réglementaires.
ARTICLE_SUMMARY = ChatProfile(
    "article summary",
    model=os.getenv("OPENAI_ARTICLE_MODEL", "gpt-5.6-luna"),
    temperature=0.3,
    max_tokens=512,
    # Huit fois le plafond classique : les 512 tokens de la réponse restent visés, mais
    # le raisonnement les consommerait entièrement avant d'écrire la première phrase.
    reasoning_max_tokens=4096,
    effort="low",
)

#: Digest audio d'une catégorie : un peu de liberté de formulation pour l'oral.
#: Sans réglage explicite, ce type d'appel tournait à la valeur par défaut, 1.0.
#: Sur un modèle raisonnant, l'effort remplace la température — `medium` parce que ce
#: prompt empile beaucoup de contraintes à satisfaire ensemble (prose, fusion, CVE, sources).
DIGEST = ChatProfile(
    "digest",
    model=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5.6-luna"),
    temperature=0.4,
    effort="medium",
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

    Deux jeux de paramètres selon la famille du modèle effectif, jamais mélangés :
    un modèle classique prend `temperature` et `max_tokens`, un modèle raisonnant
    (gpt-5 et suivants, série o) les **rejette** et prend `reasoning_effort` et
    `max_completion_tokens`. Les deux familles cohabitent dans une même exécution :
    la notation reste classique quand le digest est passé au raisonnement.
    """
    model = model or profile.model
    payload: dict = {
        "model": model,
        # Un `seed` ici rendrait les réponses reproductibles au mieux des efforts
        # du fournisseur ; la température seule n'y suffit pas.
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if is_reasoning_model(model):
        payload["reasoning_effort"] = profile.effort
        cap = profile.reasoning_max_tokens
        if cap is not None:
            payload["max_completion_tokens"] = cap
    else:
        payload["temperature"] = profile.temperature
        cap = profile.max_tokens
        if cap is not None:
            payload["max_tokens"] = cap

    response = post_json(base_url, api_key, CHAT_PATH, payload, profile.label)
    # Les compteurs de tokens ne reviennent qu'ici : c'est le seul endroit où le coût
    # de l'appel est connu. Le journal les range sous la catégorie en cours.
    runlog.record_chat(profile.label, model, response.get("usage"))

    choice = response["choices"][0]
    if choice.get("finish_reason") == "length":
        # Sans ce garde-fou, une réponse coupée ressort en erreur de parsing bien plus loin.
        # Sur un modèle raisonnant, le plafond a pu partir entièrement en raisonnement.
        raise LLMError(
            f"{PROVIDER} {profile.label}: réponse tronquée par le plafond de sortie "
            f"({cap}) sur le modèle {model}."
        )
    return (choice["message"]["content"] or "").strip()


def speak(
    base_url: str,
    api_key: str,
    model: str,
    voice: str,
    text: str,
    audio_format: str,
    instructions: str | None = None,
) -> bytes:
    """Synthèse vocale ; renvoie les octets audio.

    `instructions` dirige la diction — ton, débit, émotion, prononciation — et n'est
    accepté que par les modèles qui le prennent en charge (`gpt-4o-mini-tts` et suivants).
    Absent du payload quand il est vide : les modèles plus anciens, `tts-1` en tête,
    rejettent les paramètres qu'ils ne connaissent pas.
    """
    payload = {"model": model, "voice": voice, "input": text, "format": audio_format}
    if instructions:
        payload["instructions"] = instructions
    audio = post(base_url, api_key, SPEECH_PATH, payload, "tts")
    # La synthèse ne rend aucun compteur : le texte envoyé est la seule assiette de
    # facturation, au caractère ou au token selon le modèle. Enregistré après l'appel,
    # pour ne rien compter d'une requête rejetée.
    runlog.record_tts(model, voice, text)
    return audio
