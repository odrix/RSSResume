"""Le dialecte OpenAI.

Quatre méthodes : deux pour la complétion, deux pour la synthèse. Tout le reste —
prompts, découpage des lots, comptabilité — vient de `LLMProvider`.
"""

from __future__ import annotations

# Le module, pas le paquet : `llm/__init__.py` importe déjà celui-ci.
from rssresume.llm.base import LLMProvider
from rssresume.llm.providers import Call, Voice

#: Familles de modèles raisonnants. Elles rejettent `temperature` et `max_tokens` en 400,
#: et attendent `reasoning_effort` et `max_completion_tokens` à la place. Le test porte sur
#: le modèle, pas sur l'action : les deux familles cohabitent dans une même exécution — la
#: notation reste classique quand le digest est passé au raisonnement.
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def is_reasoning_model(model: str) -> bool:
    return (model or "").strip().lower().startswith(REASONING_PREFIXES)


class OpenAIProvider(LLMProvider):
    NAME = "openai"

    def chat_payload(self, call: Call, system: str, user: str) -> dict:
        """Deux jeux de paramètres selon la famille du modèle, jamais mélangés.

        Un `seed` ici rendrait les réponses reproductibles au mieux des efforts du
        fournisseur ; la température seule n'y suffit pas.
        """
        payload: dict = {
            "model": call.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if is_reasoning_model(call.model):
            payload["reasoning_effort"] = call.effort or "low"
            if call.max_tokens is not None:
                payload["max_completion_tokens"] = call.max_tokens
        else:
            payload["temperature"] = call.temperature
            if call.max_tokens is not None:
                payload["max_tokens"] = call.max_tokens
        return payload

    def read_chat(self, response: dict) -> tuple[str, dict | None, bool]:
        choice = response["choices"][0]
        text = (choice["message"]["content"] or "").strip()
        return text, response.get("usage"), choice.get("finish_reason") == "length"

    def speech_payload(self, voice: Voice, text: str) -> dict:
        """`instructions` dirige la diction, et n'est envoyé que s'il y en a.

        Les modèles plus anciens, `tts-1` en tête, rejettent les paramètres qu'ils ne
        connaissent pas.
        """
        payload = {
            "model": voice.model,
            "voice": voice.voice,
            "input": text,
            "format": voice.audio_format,
        }
        if voice.instructions:
            payload["instructions"] = voice.instructions
        return payload

    def read_speech(self, raw: bytes) -> bytes:
        """Le corps de la réponse *est* le fichier audio."""
        return raw
