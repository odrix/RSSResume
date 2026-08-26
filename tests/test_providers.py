"""Le choix d'un fournisseur, et la résolution de ses réglages.

L'environnement ne porte que deux choses : quel fournisseur pour quelle action, et
les clés d'API. Tout le reste sort de `providers.json`.
"""

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import llm
from rssresume.llm import providers
from rssresume.llm.mistral import MistralProvider
from rssresume.llm.openai import OpenAIProvider


class ChoiceTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_openai_is_the_default_for_every_action(self):
        for action in providers.ACTIONS:
            self.assertEqual("openai", providers.chosen(action), action)

    @mock.patch.dict(os.environ, {"RSSRESUME_PROVIDER": "mistral"}, clear=True)
    def test_one_variable_switches_everything(self):
        for action in providers.ACTIONS:
            self.assertEqual("mistral", providers.chosen(action), action)

    @mock.patch.dict(
        os.environ, {"RSSRESUME_PROVIDER": "openai", "RSSRESUME_TTS_PROVIDER": "mistral"}, clear=True
    )
    def test_an_action_can_override_the_general_choice(self):
        """Le cas d'usage : garder les résumés chez l'un, prendre la voix de l'autre."""
        self.assertEqual("openai", providers.chosen(providers.DIGEST))
        self.assertEqual("openai", providers.chosen(providers.SCORING))
        self.assertEqual("mistral", providers.chosen(providers.TTS))

    @mock.patch.dict(os.environ, {"RSSRESUME_SCORING_PROVIDER": "mistral"}, clear=True)
    def test_scoring_can_be_moved_alone(self):
        """Un petit modèle pour noter, un gros pour raconter : deux fournisseurs possibles."""
        self.assertEqual("mistral", providers.chosen(providers.SCORING))
        self.assertEqual("openai", providers.chosen(providers.DIGEST))


class SettingsTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}, clear=True)
    def test_the_api_key_is_read_from_the_provider_named_variable(self):
        self.assertTrue(providers.settings("openai").configured)
        # Chaque fournisseur n'a que la sienne : pas d'emprunt possible.
        self.assertFalse(providers.settings("mistral").configured)

    @mock.patch.dict(os.environ, {"MISTRAL_API_KEY": "cle"}, clear=True)
    def test_mistral_settings_come_from_the_json(self):
        reglages = providers.settings("mistral")

        self.assertEqual("https://api.mistral.ai/v1", reglages.base_url)
        self.assertEqual("mistral-medium-latest", reglages.call(providers.DIGEST).model)
        self.assertEqual("mistral-small-latest", reglages.call(providers.SCORING).model)
        self.assertEqual("voxtral-mini-tts-2603", reglages.voice.model)
        self.assertEqual("fr_marie_curious", reglages.voice.voice)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_an_unknown_provider_names_those_that_exist(self):
        with self.assertRaises(providers.ProviderError) as leve:
            providers.settings("anthropic")

        self.assertIn("anthropic", str(leve.exception))
        self.assertIn("mistral", str(leve.exception))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_an_undeclared_action_names_those_that_exist(self):
        with self.assertRaises(providers.ProviderError) as leve:
            providers.settings("openai").call("traduction")

        self.assertIn("traduction", str(leve.exception))
        self.assertIn("digest", str(leve.exception))


class FactoryTests(unittest.TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-openai",
            "MISTRAL_API_KEY": "cle-mistral",
            "RSSRESUME_TTS_PROVIDER": "mistral",
        },
        clear=True,
    )
    def test_each_action_gets_its_own_provider_and_its_own_key(self):
        """Le point le plus sensible du montage : ne pas envoyer la clé de l'un chez l'autre."""
        digest = llm.for_action(providers.DIGEST)
        voix = llm.for_action(providers.TTS)

        self.assertIsInstance(digest, OpenAIProvider)
        self.assertIsInstance(voix, MistralProvider)
        self.assertEqual("fr_marie_curious", voix.voice.voice)

    @mock.patch.dict(
        os.environ, {"OPENAI_API_KEY": "sk-openai", "RSSRESUME_TTS_PROVIDER": "mistral"}, clear=True
    )
    def test_an_action_without_key_yields_nothing_rather_than_borrowing_one(self):
        """Sans clé Mistral, la synthèse retombe sur espeak — pas sur la clé d'OpenAI."""
        self.assertIsNone(llm.for_action(providers.TTS))
        self.assertIsNotNone(llm.for_action(providers.DIGEST))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_without_any_key_nothing_is_built(self):
        for action in providers.ACTIONS:
            self.assertIsNone(llm.for_action(action), action)


class ProvidersFileTests(unittest.TestCase):
    def test_an_external_file_overrides_only_what_it_declares(self):
        """Surcharger un modèle ne doit pas effacer le reste du bloc du fournisseur."""
        surcharge = {"mistral": {"actions": {"digest": {"model": "mistral-large-latest"}}}}
        with tempfile.TemporaryDirectory() as tmpdir:
            chemin = pathlib.Path(tmpdir) / "providers.json"
            chemin.write_text(json.dumps(surcharge), encoding="utf-8")
            with mock.patch.dict(
                os.environ, {providers.ENV_PROVIDERS_FILE: str(chemin)}, clear=True
            ):
                reglages = providers.settings("mistral")

        self.assertEqual("mistral-large-latest", reglages.call(providers.DIGEST).model)
        # Le reste du bloc a survécu à la fusion.
        self.assertEqual("mistral-small-latest", reglages.call(providers.SCORING).model)
        self.assertEqual("fr_marie_curious", reglages.voice.voice)
        self.assertIn("voxtral-mini-tts-2603", reglages.prices)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_comment_keys_are_not_providers(self):
        self.assertEqual(["mistral", "openai"], providers.names())


class DescribeTests(unittest.TestCase):
    @mock.patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "sk-openai", "RSSRESUME_TTS_PROVIDER": "mistral"},
        clear=True,
    )
    def test_the_journal_snapshot_names_who_does_what(self):
        vu = providers.describe()

        self.assertEqual("openai", vu["digest"]["fournisseur"])
        self.assertTrue(vu["digest"]["actif"])
        self.assertEqual("mistral", vu["tts"]["fournisseur"])
        # Pas de clé Mistral : la synthèse retombera sur espeak, et le journal le dit.
        self.assertFalse(vu["tts"]["actif"])
        self.assertEqual("fr_marie_curious", vu["tts"]["voix"])


if __name__ == "__main__":
    unittest.main()
