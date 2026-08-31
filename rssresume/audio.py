"""Synthèse vocale du résumé : celle du fournisseur, ou `espeak` en local."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from rssresume.llm import LLMProvider
from rssresume.tools import console, duration
from rssresume.tools.text import decouper

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
        # Le texte est découpé avant d'être annoncé : le nombre d'appels fait partie de
        # ce qu'on veut lire dans le suivi, une journée en trois morceaux se paie trois fois.
        morceaux = decouper(text, voice.input_limit or 0) or [text or ""]
        console.detail(
            f"synthèse vocale via {self._provider.name} — {voice.model} (voix {voice.voice}"
            + (", consignes de diction" if voice.instructions else "")
            + (f", {len(morceaux)} segments" if len(morceaux) > 1 else "")
            + ")"
        )
        output_path.write_bytes(self._rabouter(morceaux))
        return output_path

    def _rabouter(self, morceaux: list[str]) -> bytes:
        """Les morceaux synthétisés bout à bout, le tag ID3 des reprises retiré.

        Chaque appel rend un fichier complet, donc précédé de son propre tag. Collés tels
        quels, ces tags se retrouvent au milieu du son : le parcours des trames de
        `duration.py` s'y arrête, et l'email annoncerait la durée du premier morceau pour
        celle de la journée. Les lecteurs, eux, savent les enjamber — c'est la mesure qui
        ne le sait pas, et c'est elle qui décide si on lance l'écoute.
        """
        segments = [self._provider.speak(morceau) for morceau in morceaux]
        return b"".join(
            segment if rang == 0 else segment[duration.apres_id3(segment) :]
            for rang, segment in enumerate(segments)
        )

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
