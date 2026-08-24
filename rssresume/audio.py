"""Synthèse vocale des résumés (API compatible OpenAI, sinon espeak)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from rssresume import console
from rssresume.config import AppConfig
from rssresume import llm

OPENAI_EXTENSION = ".mp3"
ESPEAK_EXTENSION = ".wav"


def audio_extension(config: AppConfig) -> str:
    """Extension du fichier audio selon le moteur de synthèse retenu."""
    return OPENAI_EXTENSION if config.uses_llm else ESPEAK_EXTENSION


class AudioGenerator:
    def __init__(self, config: AppConfig):
        self._config = config

    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._config.uses_llm:
            return self._synthesize_with_openai(text, output_path)
        return self._synthesize_with_espeak(text, output_path)

    def _synthesize_with_openai(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        console.detail(
            f"synthèse vocale via l'API {self._config.tts_model} (voix {self._config.tts_voice}"
            + (", consignes de diction)" if self._config.tts_instructions else ")")
        )
        audio = llm.speak(
            self._config.llm_base_url,
            self._config.llm_api_key,
            self._config.tts_model,
            self._config.tts_voice,
            text,
            output_path.suffix.lstrip(".") or OPENAI_EXTENSION.lstrip("."),
            self._config.tts_instructions,
        )
        output_path.write_bytes(audio)
        return output_path

    @staticmethod
    def _synthesize_with_espeak(text: str, output_path: pathlib.Path) -> pathlib.Path:
        if not shutil.which("espeak"):
            raise RuntimeError(
                "No text-to-speech backend available. Install espeak or configure OPENAI_BASE_URL and OPENAI_API_KEY."
            )
        console.detail("synthèse vocale via espeak")
        subprocess.run(
            ["espeak", "--stdin", "-w", str(output_path)],
            input=text.encode("utf-8"),
            check=True,
        )
        return output_path
