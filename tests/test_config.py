import os
import pathlib
import unittest
from unittest import mock

from rssresume.config import AppConfig
from rssresume.profil import DEFAULT_PROFIL, ENV_PROFIL

BASE_ENV = {
    "FRESHRSS_BASE_URL": "https://example.com",
    "FRESHRSS_USERNAME": "user",
    "FRESHRSS_API_PASSWORD": "password",
}


class AppConfigTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {**BASE_ENV, "OPENAI_API_KEY": "token", "RSSRESUME_OUTPUT_DIR": "   "}, clear=True)
    def test_from_env_defaults_output_dir_and_openai_base_url(self):
        config = AppConfig.from_env()

        self.assertEqual(pathlib.Path("output"), config.output_dir)
        self.assertEqual("https://api.openai.com/v1", config.llm_base_url)
        self.assertTrue(config.uses_llm)

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_without_api_key_disables_llm(self):
        config = AppConfig.from_env()

        self.assertIsNone(config.llm_base_url)
        self.assertFalse(config.uses_llm)

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, "RSSRESUME_CATEGORIES": " Tech , News ", "RSSRESUME_EXCLUDED_CATEGORIES": "Non classé"},
        clear=True,
    )
    def test_from_env_parses_category_lists(self):
        config = AppConfig.from_env()

        self.assertEqual(["Tech", "News"], config.categories)
        self.assertEqual(["Non classé"], config.excluded_categories)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_env_lists_missing_required_variables(self):
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn("FRESHRSS_BASE_URL", str(raised.exception))


    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, "OPENAI_TTS_INSTRUCTIONS": '"""Voix posée.\\nDébit modéré."""'},
        clear=True,
    )
    def test_from_env_unquotes_and_unescapes_the_tts_instructions(self):
        """Le chargeur .env documenté laisse les guillemets et écrit les sauts de ligne `\\n`."""
        self.assertEqual(
            "Voix posée.\nDébit modéré.", AppConfig.from_env().tts_instructions
        )

    @mock.patch.dict(os.environ, {**BASE_ENV, "OPENAI_TTS_INSTRUCTIONS": "   "}, clear=True)
    def test_from_env_treats_blank_tts_instructions_as_absent(self):
        self.assertIsNone(AppConfig.from_env().tts_instructions)

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_falls_back_to_the_default_profile(self):
        self.assertEqual(DEFAULT_PROFIL, AppConfig.from_env().profil)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_PROFIL: "Vigneronne en Anjou."}, clear=True)
    def test_from_env_reads_an_injected_profile(self):
        """Le profil est résolu une fois au démarrage, pas à chaque prompt."""
        self.assertEqual("Vigneronne en Anjou.", AppConfig.from_env().profil)


if __name__ == "__main__":
    unittest.main()
