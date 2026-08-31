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
from rssresume.tools import duration
from tests.test_duration import DUREE_TRAME, mp3, tag_id3

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


def openai_provider(instructions=None, audio_format="mp3", input_limit=None):
    return make_provider(
        OpenAIProvider,
        Voice("gpt-4o-mini-tts", "alloy", audio_format, instructions, input_limit),
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


def synthesize_long(provider, texte, reponses):
    """Comme `synthesize`, mais avec une réponse par appel : renvoie (payloads, octets)."""
    generator = AudioGenerator(provider)
    with tempfile.TemporaryDirectory() as tmpdir:
        chemin = pathlib.Path(tmpdir) / f"journee{generator.extension}"
        with mock.patch.object(type(provider), "_post", side_effect=reponses) as post:
            generator.synthesize(texte, chemin)
        return [appel.args[1] for appel in post.call_args_list], chemin.read_bytes()


class DecoupageTests(unittest.TestCase):
    """Ce que ces tests protègent : `/v1/audio/speech` refuse une entrée trop longue —
    elle n'est pas tronquée, l'appel échoue et la journée est perdue. Le texte part donc
    en plusieurs appels, dont les audios sont raboutés en un seul fichier."""

    #: Trois phrases identiques de 28 signes : sous un plafond de 60, elles se rangent
    #: deux d'un côté, une de l'autre — deux appels, coupés sur une fin de phrase.
    TEXTE = ("Une phrase de trente signes. " * 3).strip()

    def test_a_text_over_the_limit_is_sent_in_several_calls(self):
        payloads, _ = synthesize_long(
            openai_provider(input_limit=60), self.TEXTE, [b"un", b"deux"]
        )

        self.assertEqual(2, len(payloads))
        for payload in payloads:
            self.assertLessEqual(len(payload["input"]), 60)
        # Aucun mot n'est perdu en route : c'est tout le texte qui est dit.
        self.assertEqual(
            self.TEXTE.split(), " ".join(p["input"] for p in payloads).split()
        )

    def test_without_a_declared_limit_the_text_goes_in_one_call(self):
        """Un fournisseur qui n'annonce pas de plafond reçoit son texte d'un seul tenant."""
        payloads, audio = synthesize_long(openai_provider(), self.TEXTE, [b"tout"])

        self.assertEqual([self.TEXTE], [payload["input"] for payload in payloads])
        self.assertEqual(b"tout", audio)

    def test_the_segments_land_in_a_single_file(self):
        _, audio = synthesize_long(
            openai_provider(input_limit=60), self.TEXTE, [b"debut", b"fin"]
        )

        self.assertEqual(b"debutfin", audio)

    def test_the_id3_tag_of_a_resumed_segment_is_dropped(self):
        """Sans cela le parcours des trames s'arrête au tag, et la durée annoncée est
        celle du premier morceau — le sous-titre de l'email promettrait la moitié."""
        segments = [tag_id3(b"pochette" * 4) + mp3(10) for _ in range(2)]

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = AudioGenerator(openai_provider(input_limit=60))
            chemin = pathlib.Path(tmpdir) / "journee.mp3"
            with mock.patch.object(OpenAIProvider, "_post", side_effect=segments):
                generator.synthesize(self.TEXTE, chemin)

            # Le tag du premier est gardé — c'est celui du fichier —, celui du second non.
            self.assertEqual(segments[0] + mp3(10), chemin.read_bytes())
            self.assertAlmostEqual(20 * DUREE_TRAME, duration.seconds(chemin), places=5)


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
