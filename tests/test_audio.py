"""Le générateur audio : ce qu'il écrit, et avec quel moteur."""

import base64
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.audio import AudioGenerator
from rssresume.llm.mistral import MistralProvider
from rssresume.llm.openai import OpenAIProvider
from rssresume.llm.providers import Settings, Voice

CONSIGNES = "Voix posée, débit modéré, ton sincère."


def make_provider(classe, voice):
    return classe(
        Settings(
            name=classe.NAME,
            label=classe.NAME.title(),
            base_url="https://api.example/v1",
            api_key="key",
            calls={},
            voice=voice,
            prices={},
        )
    )


def openai_provider(instructions=None, audio_format="mp3"):
    return make_provider(
        OpenAIProvider,
        Voice("gpt-4o-mini-tts", "alloy", audio_format, instructions),
    )


def mistral_provider():
    return make_provider(
        MistralProvider, Voice("voxtral-mini-tts-2603", "fr_marie_curious", "mp3")
    )


def synthesize(provider, reponse):
    """Écrit l'audio en interceptant le POST ; renvoie (payload, octets écrits)."""
    generator = AudioGenerator(provider)
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch.object(type(provider), "_post", return_value=reponse) as post:
            path = generator.synthesize(
                "Le résumé du jour.", pathlib.Path(tmpdir) / f"tech{generator.extension}"
            )
        return post.call_args.args[1], path.read_bytes(), path.name


class OpenAISpeechTests(unittest.TestCase):
    def test_instructions_are_sent_when_configured(self):
        payload, audio, name = synthesize(openai_provider(CONSIGNES), b"octets-audio")

        self.assertEqual(CONSIGNES, payload["instructions"])
        self.assertEqual("gpt-4o-mini-tts", payload["model"])
        self.assertEqual("alloy", payload["voice"])
        self.assertEqual("Le résumé du jour.", payload["input"])
        self.assertEqual(b"octets-audio", audio)
        self.assertEqual("tech.mp3", name)

    def test_the_parameter_is_absent_without_instructions(self):
        """`tts-1` rejette les paramètres qu'il ne connaît pas : mieux vaut ne rien envoyer."""
        payload, _, _ = synthesize(openai_provider(), b"octets-audio")

        self.assertNotIn("instructions", payload)


class MistralSpeechTests(unittest.TestCase):
    """La voix peut venir d'un fournisseur, les résumés d'un autre."""

    def test_the_base64_envelope_is_unwrapped_before_being_written(self):
        enveloppe = json.dumps({"audio_data": base64.b64encode(b"octets-audio").decode()}).encode()

        payload, audio, name = synthesize(mistral_provider(), enveloppe)

        self.assertEqual("voxtral-mini-tts-2603", payload["model"])
        self.assertEqual("fr_marie_curious", payload["voice_id"])
        # Ce qui atterrit sur le disque est un fichier audio, pas du JSON.
        self.assertEqual(b"octets-audio", audio)
        self.assertEqual("tech.mp3", name)


class ExtensionTests(unittest.TestCase):
    def test_the_extension_follows_the_declared_format(self):
        self.assertEqual(".mp3", AudioGenerator(openai_provider()).extension)
        self.assertEqual(
            ".wav", AudioGenerator(openai_provider(audio_format="wav")).extension
        )

    def test_without_a_provider_the_file_is_the_espeak_wav(self):
        self.assertEqual(".wav", AudioGenerator(None).extension)

    def test_without_a_provider_and_without_espeak_the_error_names_the_way_out(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("rssresume.audio.shutil.which", return_value=None):
                with self.assertRaises(RuntimeError) as leve:
                    AudioGenerator(None).synthesize("texte", pathlib.Path(tmpdir) / "a.wav")

        self.assertIn("MISTRAL_API_KEY", str(leve.exception))


if __name__ == "__main__":
    unittest.main()
