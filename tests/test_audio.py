"""Synthèse vocale : ce qui part effectivement au fournisseur."""

import dataclasses
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.audio import AudioGenerator, audio_extension
from support import make_config

CONSIGNES = "Voix posée, débit modéré, ton sincère."


def make_tts_config(tmpdir, instructions=None):
    return dataclasses.replace(
        make_config(tmpdir),
        llm_base_url="https://api.example/v1",
        llm_api_key="key",
        tts_model="gpt-4o-mini-tts",
        tts_voice="alloy",
        tts_instructions=instructions,
    )


def synthesize(config, tmpdir):
    """Lance la synthèse en interceptant le POST, et renvoie le payload envoyé."""
    with mock.patch("rssresume.llm.post", return_value=b"octets-audio") as post:
        path = AudioGenerator(config).synthesize(
            "Le résumé du jour.", pathlib.Path(tmpdir) / f"tech{audio_extension(config)}"
        )
    assert path.read_bytes() == b"octets-audio"
    return post.call_args.args[3]


class SpeechPayloadTests(unittest.TestCase):
    def test_instructions_are_sent_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = synthesize(make_tts_config(tmpdir, CONSIGNES), tmpdir)

        self.assertEqual(CONSIGNES, payload["instructions"])
        self.assertEqual("gpt-4o-mini-tts", payload["model"])
        self.assertEqual("alloy", payload["voice"])
        self.assertEqual("Le résumé du jour.", payload["input"])

    def test_the_parameter_is_absent_without_instructions(self):
        """`tts-1` rejette les paramètres qu'il ne connaît pas : mieux vaut ne rien envoyer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = synthesize(make_tts_config(tmpdir), tmpdir)

        self.assertNotIn("instructions", payload)


if __name__ == "__main__":
    unittest.main()
