"""Synthèse vocale du résumé : celle du fournisseur, ou `espeak` en local."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from rssresume.llm import LLMProvider
from rssresume.tools import console

ESPEAK_EXTENSION = ".wav"


class AudioGenerator:
    """Dit un texte. Sans fournisseur, `espeak` — sous réserve qu'il soit installé."""

    def __init__(self, provider: LLMProvider | None = None):
        self._provider = provider

    @property
    def extension(self) -> str:
        """Extension du fichier à écrire, dictée par le format que le fournisseur rend.

        L'écrire avec la mauvaise donnerait un fichier que les lecteurs refusent.
        """
        if self._provider is None:
            return ESPEAK_EXTENSION
        return f".{self._provider.voice.audio_format}"

    def synthesize(self, text: str, output_path: pathlib.Path) -> pathlib.Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._provider is None:
            return self._synthesize_with_espeak(text, output_path)

        voice = self._provider.voice
        console.detail(
            f"synthèse vocale via {self._provider.name} — {voice.model} (voix {voice.voice}"
            + (", consignes de diction)" if voice.instructions else ")")
        )
        output_path.write_bytes(self._provider.speak(text))
        return output_path

    @staticmethod
    def _synthesize_with_espeak(text: str, output_path: pathlib.Path) -> pathlib.Path:
        if not shutil.which("espeak"):
            raise RuntimeError(
                "No text-to-speech backend available. Install espeak, or set the API key of "
                "the provider chosen for TTS (OPENAI_API_KEY, MISTRAL_API_KEY…)."
            )
        console.detail("synthèse vocale via espeak")
        subprocess.run(
            ["espeak", "--stdin", "-w", str(output_path)],
            input=text.encode("utf-8"),
            check=True,
        )
        return output_path
