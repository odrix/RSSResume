"""Ce que chaque fournisseur met sur le fil, et ce qu'il sait relire.

Un `LLMProvider` reçoit ses réglages au constructeur : les tests en fabriquent, sans
toucher à l'environnement ni à `providers.json`. Seul le POST est coupé.
"""

import base64
import json
import unittest
from unittest import mock

from rssresume import llm
from rssresume.llm import providers
from rssresume.llm.mistral import MistralProvider
from rssresume.llm.openai import OpenAIProvider, is_reasoning_model
from rssresume.llm.providers import Call, Settings, Voice

REPONSE = {"choices": [{"message": {"content": "  texte  "}, "finish_reason": "stop"}]}

CLASSIQUE = Call("digest", "gpt-4o-mini", temperature=0.4, max_tokens=512)
RAISONNANT = Call("digest", "gpt-5.6-luna", temperature=0.4, max_tokens=4096, effort="medium")


def make(classe, call=CLASSIQUE, voice=None):
    """Un fournisseur réglé pour ce test, et rien d'autre."""
    return classe(
        Settings(
            name=classe.NAME,
            label=classe.NAME.title(),
            base_url="https://api.example/v1",
            api_key="key",
            calls={call.action: call},
            voice=voice or Voice(model="modele-tts", voice="une-voix", audio_format="mp3"),
            prices={},
        )
    )


def digest_call(provider, reponse=REPONSE):
    """Lance un digest en interceptant le POST ; renvoie (chemin, payload)."""
    with mock.patch.object(type(provider), "_post", return_value=json.dumps(reponse).encode()) as p:
        provider.write_digest("Tech", [{"title": "T", "content": "C"}])
    path, payload, _ = p.call_args.args
    return path, payload


class FamilyDetectionTests(unittest.TestCase):
    def test_reasoning_families_are_recognized(self):
        for model in ("gpt-5-mini", "gpt-5.6-luna", "GPT-5.6-Terra", "o3-mini", "o4-mini"):
            self.assertTrue(is_reasoning_model(model), model)

    def test_classic_families_are_not(self):
        for model in ("gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "mistral-medium-latest", "", None):
            self.assertFalse(is_reasoning_model(model), model)


class OpenAIPayloadTests(unittest.TestCase):
    def test_a_classic_model_gets_temperature_and_max_tokens(self):
        _, payload = digest_call(make(OpenAIProvider, CLASSIQUE))

        self.assertEqual(0.4, payload["temperature"])
        self.assertEqual(512, payload["max_tokens"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("max_completion_tokens", payload)

    def test_a_reasoning_model_gets_effort_and_max_completion_tokens(self):
        """`temperature` et `max_tokens` sont rejetés en 400 par ces modèles."""
        _, payload = digest_call(make(OpenAIProvider, RAISONNANT))

        self.assertEqual("medium", payload["reasoning_effort"])
        self.assertEqual(4096, payload["max_completion_tokens"])
        self.assertNotIn("temperature", payload)
        self.assertNotIn("max_tokens", payload)

    def test_a_call_without_cap_sends_none(self):
        sans_plafond = Call("digest", "gpt-5.6-luna", temperature=0.4)

        _, payload = digest_call(make(OpenAIProvider, sans_plafond))

        self.assertNotIn("max_completion_tokens", payload)
        # Faute d'effort déclaré, le moins cher : le raisonnement est facturé en sortie.
        self.assertEqual("low", payload["reasoning_effort"])

    def test_a_truncated_answer_names_the_effective_cap(self):
        tronquee = {"choices": [{"message": {"content": "à moiti"}, "finish_reason": "length"}]}

        with self.assertRaises(llm.LLMError) as leve:
            digest_call(make(OpenAIProvider, RAISONNANT), reponse=tronquee)

        self.assertIn("4096", str(leve.exception))
        self.assertIn("gpt-5.6-luna", str(leve.exception))


class MistralPayloadTests(unittest.TestCase):
    def test_the_reasoning_parameters_are_never_sent(self):
        """Mistral rejette `reasoning_effort` et `max_completion_tokens` en 400."""
        _, payload = digest_call(make(MistralProvider, RAISONNANT))

        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual(0.4, payload["temperature"])
        self.assertEqual(4096, payload["max_tokens"])

    def test_the_completion_path_is_the_openai_compatible_one(self):
        path, payload = digest_call(make(MistralProvider))

        self.assertEqual("/chat/completions", path)
        self.assertEqual(["system", "user"], [m["role"] for m in payload["messages"]])

    def test_a_window_overflow_is_a_truncation_too(self):
        """Mistral rend `model_length` là où OpenAI rend `length` : même symptôme."""
        coupee = {"choices": [{"message": {"content": "x"}, "finish_reason": "model_length"}]}

        with self.assertRaises(llm.LLMError):
            digest_call(make(MistralProvider), reponse=coupee)


class SpeechTests(unittest.TestCase):
    """La synthèse est le point où les deux fournisseurs divergent vraiment."""

    @staticmethod
    def _speak(provider, reponse):
        with mock.patch.object(type(provider), "_post", return_value=reponse) as post:
            audio = provider.speak("Bonjour.")
        path, payload, _ = post.call_args.args
        return path, payload, audio

    def test_openai_sends_voice_and_reads_the_body_as_audio(self):
        voice = Voice(model="gpt-4o-mini-tts", voice="alloy", instructions="Ton posé.")

        path, payload, audio = self._speak(make(OpenAIProvider, voice=voice), b"octets-audio")

        self.assertEqual("/audio/speech", path)
        self.assertEqual("alloy", payload["voice"])
        self.assertEqual("mp3", payload["format"])
        self.assertEqual("Ton posé.", payload["instructions"])
        self.assertEqual(b"octets-audio", audio)

    def test_openai_omits_the_instructions_when_there_are_none(self):
        """`tts-1` rejette les paramètres qu'il ne connaît pas."""
        _, payload, _ = self._speak(make(OpenAIProvider), b"a")

        self.assertNotIn("instructions", payload)

    def test_mistral_sends_voice_id_and_decodes_the_base64_envelope(self):
        voice = Voice(model="voxtral-mini-tts-2603", voice="fr_marie_curious")
        enveloppe = json.dumps({"audio_data": base64.b64encode(b"octets-audio").decode()}).encode()

        path, payload, audio = self._speak(make(MistralProvider, voice=voice), enveloppe)

        self.assertEqual("/audio/speech", path)
        self.assertEqual("fr_marie_curious", payload["voice_id"])
        self.assertEqual("mp3", payload["response_format"])
        self.assertNotIn("voice", payload)
        self.assertNotIn("format", payload)
        self.assertEqual(b"octets-audio", audio)

    def test_mistral_never_forwards_the_diction_instructions(self):
        """`/audio/speech` n'a pas de champ pour elles : les envoyer ferait un 400."""
        voice = Voice(model="voxtral", voice="fr_marie_curious", instructions="Ton posé.")
        enveloppe = json.dumps({"audio_data": base64.b64encode(b"a").decode()}).encode()

        _, payload, _ = self._speak(make(MistralProvider, voice=voice), enveloppe)

        self.assertNotIn("instructions", payload)

    def test_an_envelope_without_audio_is_an_llm_error(self):
        with self.assertRaises(llm.LLMError) as leve:
            self._speak(make(MistralProvider), b'{"message": "quota atteint"}')

        self.assertIn("audio_data", str(leve.exception))


class FactoryTests(unittest.TestCase):
    def test_each_provider_gets_its_own_adapter(self):
        self.assertIsInstance(llm.build(providers.settings("openai")), OpenAIProvider)
        self.assertIsInstance(llm.build(providers.settings("mistral")), MistralProvider)

    def test_a_provider_without_adapter_says_so(self):
        orphelin = providers.settings("openai")
        orphelin = type(orphelin)(**{**orphelin.__dict__, "name": "anthropic"})

        with self.assertRaises(llm.LLMError) as leve:
            llm.build(orphelin)

        self.assertIn("anthropic", str(leve.exception))
        self.assertIn("openai", str(leve.exception))


class ShippedSettingsTests(unittest.TestCase):
    """Les défauts que `providers.json` porte pour chaque fournisseur."""

    def test_every_provider_declares_every_action(self):
        """Un fournisseur amputé d'une action casserait le pipeline à mi-course."""
        for name in providers.names():
            reglages = providers.settings(name)
            for action in (providers.SCORING, providers.ARTICLE, providers.DIGEST):
                self.assertTrue(reglages.call(action).model, f"{name}/{action}")
            self.assertTrue(reglages.voice.model, f"{name}/tts")
            self.assertTrue(reglages.voice.voice, f"{name}/tts")

    def test_openai_scoring_stays_on_a_classic_model(self):
        """Changer le modèle de notation change l'empreinte du prompt, donc renote tout."""
        self.assertFalse(
            is_reasoning_model(providers.settings("openai").call(providers.SCORING).model)
        )

    def test_openai_keeps_its_diction_instructions(self):
        instructions = providers.settings("openai").voice.instructions

        self.assertIsNotNone(instructions)
        self.assertIn("A.N.S.S.I.", instructions)

    def test_mistral_ships_the_french_voice_and_no_instructions(self):
        voice = providers.settings("mistral").voice

        self.assertEqual("voxtral-mini-tts-2603", voice.model)
        self.assertEqual("fr_marie_curious", voice.voice)
        # `/audio/speech` n'a pas de champ pour des consignes : n'en promettons aucune.
        self.assertIsNone(voice.instructions)


if __name__ == "__main__":
    unittest.main()
