import os
import pathlib
import unittest
from unittest import mock

from rssresume.config import AppConfig

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


if __name__ == "__main__":
    unittest.main()
