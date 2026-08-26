"""Le dialecte Mistral.

Deux écarts avec OpenAI, et ce sont eux qui justifient d'avoir séparé les adaptateurs :

- les complétions sont compatibles, mais ne connaissent ni `reasoning_effort` ni
  `max_completion_tokens` — les envoyer fait un 400 ;
- la synthèse vocale ne l'est pas du tout : le champ s'appelle `voice_id`, le format
  `response_format`, il n'y a pas de consignes de diction, et la réponse est un objet
  JSON dont l'audio est encodé en base64 plutôt que le fichier lui-même.
"""

from __future__ import annotations

import base64
import binascii
import json

# Le module, pas le paquet : `llm/__init__.py` importe déjà celui-ci.
from rssresume.llm.base import LLMProvider
from rssresume.llm.providers import Call, Voice

#: Champ de la réponse de synthèse qui porte l'audio.
AUDIO_FIELD = "audio_data"


class MistralProvider(LLMProvider):
    NAME = "mistral"

    def chat_payload(self, call: Call, system: str, user: str) -> dict:
        """Un seul jeu de paramètres.

        Mistral pilote ses modèles hybrides depuis le prompt, pas depuis un bouton
        d'effort : `call.effort` est ignoré ici, volontairement et non par oubli.
        """
        payload: dict = {
            "model": call.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": call.temperature,
        }
        if call.max_tokens is not None:
            payload["max_tokens"] = call.max_tokens
        return payload

    def read_chat(self, response: dict) -> tuple[str, dict | None, bool]:
        choice = response["choices"][0]
        text = (choice["message"]["content"] or "").strip()
        # `model_length` quand c'est la fenêtre du modèle qui a été atteinte plutôt que le
        # plafond demandé. Les deux sont des réponses coupées, et se rattrapent pareil.
        tronquee = choice.get("finish_reason") in ("length", "model_length")
        return text, response.get("usage"), tronquee

    def speech_payload(self, voice: Voice, text: str) -> dict:
        """`voice.instructions` est ignoré : `/audio/speech` n'a pas de champ pour lui.

        Le fournisseur n'en déclare d'ailleurs aucune dans `providers.json` — chez lui,
        tout se joue dans le choix de la voix.
        """
        return {
            "model": voice.model,
            "input": text,
            # `voice_id`, pas `voice` : un identifiant de préréglage (`fr_marie_curious`)
            # ou d'une voix clonée enregistrée sur le compte.
            "voice_id": voice.voice,
            "response_format": voice.audio_format,
            # Le mode flux rendrait un event-stream ; on veut un fichier d'un bloc.
            "stream": False,
        }

    def read_speech(self, raw: bytes) -> bytes:
        try:
            encoded = json.loads(raw.decode("utf-8"))[AUDIO_FIELD]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(
                f"réponse inattendue, champ '{AUDIO_FIELD}' introuvable ({raw[:200]!r})"
            ) from exc
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"'{AUDIO_FIELD}' non décodable en base64 : {exc}") from exc
