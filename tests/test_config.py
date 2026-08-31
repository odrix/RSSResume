"""Ce qu'`AppConfig` lit encore : FreshRSS, les catégories, le seuil, le SMTP.

Tout ce qui concerne les fournisseurs de LLM est passé dans `test_providers.py`.
"""

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.config import (
    AUDIO_MODE_CATEGORY,
    AUDIO_MODE_GLOBAL,
    DEFAULT_ARTICLE_CHAR_LIMIT,
    DEFAULT_TIMEZONE,
    ENV_ARTICLE_CHAR_LIMIT,
    ENV_AUDIO_MODE,
    ENV_CERTFR_CATEGORIES,
    ENV_DEBUG,
    ENV_MAIL_TRANSPORT,
    ENV_RESEND_API_KEY,
    ENV_SMTP_TO,
    ENV_TIMEZONE,
    MAIL_TRANSPORT_RESEND,
    MAIL_TRANSPORT_SMTP,
    AppConfig,
)
from rssresume.profil import DEFAULT_PROFIL, ENV_PROFIL, ENV_PROFIL_FILE

BASE_ENV = {
    "FRESHRSS_BASE_URL": "https://example.com",
    "FRESHRSS_USERNAME": "user",
    "FRESHRSS_API_PASSWORD": "password",
}


class AppConfigTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {**BASE_ENV, "RSSRESUME_OUTPUT_DIR": "   "}, clear=True)
    def test_from_env_defaults_the_output_dir(self):
        self.assertEqual(pathlib.Path("output"), AppConfig.from_env().output_dir)

    @mock.patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "RSSRESUME_CATEGORIES": " Tech , News ",
            "RSSRESUME_EXCLUDED_CATEGORIES": "Non classé",
        },
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
        {**BASE_ENV, "RSSRESUME_SCORE_THRESHOLD": "5", "RSSRESUME_MAX_DIGEST_ITEMS": "3"},
        clear=True,
    )
    def test_from_env_reads_the_selection_settings(self):
        config = AppConfig.from_env()

        self.assertEqual(5, config.score_threshold)
        self.assertEqual(3, config.max_digest_items)

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_defaults_the_fallback_settings(self):
        """Le repli est actif par défaut : cinq articles, en descendant jusqu'au score 5."""
        config = AppConfig.from_env()

        self.assertEqual(5, config.fallback_threshold)
        self.assertEqual(5, config.min_digest_items)
        self.assertEqual({}, config.category_thresholds)

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, "RSSRESUME_CATEGORY_THRESHOLDS": "6 - Tech generaliste=5, Veille = 6 "},
        clear=True,
    )
    def test_from_env_parses_the_per_category_thresholds(self):
        config = AppConfig.from_env()

        self.assertEqual(
            {"6 - tech generaliste": 5, "veille": 6}, config.category_thresholds
        )

    @mock.patch.dict(
        os.environ, {**BASE_ENV, "RSSRESUME_CATEGORY_THRESHOLDS": "Tech generaliste"}, clear=True
    )
    def test_a_malformed_category_threshold_fails_at_startup(self):
        """Un seuil qu'on croit posé et qui ne l'est pas ne se voit qu'après des digests vides."""
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn("RSSRESUME_CATEGORY_THRESHOLDS", str(raised.exception))

    @mock.patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "RSSRESUME_SCORE_THRESHOLD": "7",
            "RSSRESUME_CATEGORY_THRESHOLDS": "6 - Tech generaliste=5",
            "RSSRESUME_FALLBACK_THRESHOLD": "5",
            "RSSRESUME_MIN_DIGEST_ITEMS": "4",
            "RSSRESUME_MAX_DIGEST_ITEMS": "9",
        },
        clear=True,
    )
    def test_the_selection_rule_of_a_category_carries_its_own_threshold(self):
        config = AppConfig.from_env()

        generaliste = config.selection_rule("6 - TECH GENERALISTE")
        cyber = config.selection_rule("2 - Cybersecurite")

        self.assertEqual(5, generaliste.seuil)
        self.assertEqual(7, cyber.seuil)
        # Repli et plafond, eux, répondent au volume d'une journée : ils sont communs.
        self.assertEqual((5, 4, 9), (cyber.seuil_repli, cyber.minimum, cyber.plafond))

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_falls_back_to_the_default_profile(self):
        self.assertEqual(DEFAULT_PROFIL, AppConfig.from_env().profil)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_PROFIL: "Vigneronne en Anjou."}, clear=True)
    def test_from_env_reads_an_injected_profile(self):
        """Le profil est résolu une fois au démarrage, pas à chaque prompt."""
        self.assertEqual("Vigneronne en Anjou.", AppConfig.from_env().profil)


class DocumentDeProfilTests(unittest.TestCase):
    """Un seul document apporte le profil, la stack et le destinataire du digest."""

    def _config(self, document):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "profile.json"
            fichier.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            env = {**BASE_ENV, ENV_PROFIL_FILE: str(fichier)}

            with mock.patch.dict(os.environ, env, clear=True):
                return AppConfig.from_env()

    def test_the_document_carries_the_profile_the_stack_and_the_recipient(self):
        config = self._config(
            {
                "profil": "Vigneronne en Anjou.",
                "stack": ["Traefik"],
                "email": "moi@example.com",
            }
        )

        self.assertEqual("Vigneronne en Anjou.", config.profil)
        self.assertEqual(("Traefik",), config.stack.concernes("Vulnérabilité dans Traefik"))
        self.assertEqual(["moi@example.com"], config.smtp_to)

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_without_a_document_the_stack_is_empty_and_nobody_is_written_to(self):
        config = AppConfig.from_env()

        self.assertTrue(config.stack.vide)
        self.assertEqual([], config.smtp_to)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_SMTP_TO: "dest@example.com"}, clear=True)
    def test_the_old_smtp_to_variable_is_refused(self):
        """Laissée en place, elle ferait croire à un destinataire et le digest ne partirait plus."""
        with self.assertRaises(ValueError) as leve:
            AppConfig.from_env()

        self.assertIn(ENV_SMTP_TO, str(leve.exception))


class CertfrCategoriesTests(unittest.TestCase):
    """Les catégories routées hors du pipeline LLM, vers le traitement déterministe."""

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_nothing_is_routed_by_default(self):
        """Le routage est explicite : aucune catégorie n'y tombe parce qu'elle s'appelle CERT-FR."""
        config = AppConfig.from_env()

        self.assertEqual([], config.certfr_categories)
        self.assertFalse(config.est_deterministe("1 - Alertes et avis CERT-FR ANSSI"))

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, ENV_CERTFR_CATEGORIES: " 1 - Alertes et avis CERT-FR ANSSI , Veille CVE "},
        clear=True,
    )
    def test_from_env_parses_the_routed_category_list(self):
        config = AppConfig.from_env()

        self.assertEqual(
            ["1 - Alertes et avis CERT-FR ANSSI", "Veille CVE"], config.certfr_categories
        )
        self.assertTrue(config.est_deterministe("1 - Alertes et avis CERT-FR ANSSI"))
        self.assertFalse(config.est_deterministe("2 - Cybersecurite technique"))

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, ENV_CERTFR_CATEGORIES: "1 - alertes et avis cert-fr anssi"},
        clear=True,
    )
    def test_the_comparison_drops_the_accents_as_well_as_the_case(self):
        """Le libellé réel porte des accents ; la variable les perd à chaque copier-coller.

        `.env.local` contient déjà un `RSSRESUME_CATEGORY_THRESHOLDS` écrit sans accents :
        une catégorie qu'on croit routée et qui ne l'est pas repasse par le LLM tous les
        matins, sans que rien ne le signale.
        """
        self.assertTrue(
            AppConfig.from_env().est_deterministe("1 - Alertes et avis CERT-FR ANSSI")
        )

    @mock.patch.dict(
        os.environ, {**BASE_ENV, ENV_CERTFR_CATEGORIES: "Alertes CERT-FR=7"}, clear=True
    )
    def test_an_entry_written_like_a_threshold_fails_at_startup(self):
        """La faute vient de la variable voisine, qui, elle, prend « Catégorie=score »."""
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn(ENV_CERTFR_CATEGORIES, str(raised.exception))

    @mock.patch.dict(
        os.environ, {**BASE_ENV, ENV_CERTFR_CATEGORIES: "Alertes CERT-FR, ---"}, clear=True
    )
    def test_an_entry_without_a_single_word_fails_at_startup(self):
        with self.assertRaises(ValueError):
            AppConfig.from_env()


class TimezoneTests(unittest.TestCase):
    """Le fuseau qui découpe les journées, résolu une fois au lancement."""

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_the_day_is_cut_in_paris_by_default(self):
        """En UTC, un article publié à 1 h du matin à Paris tombait dans la veille."""
        self.assertEqual(DEFAULT_TIMEZONE, str(AppConfig.from_env().timezone))

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_TIMEZONE: "America/Montreal"}, clear=True)
    def test_the_timezone_is_configurable(self):
        self.assertEqual("America/Montreal", str(AppConfig.from_env().timezone))

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_TIMEZONE: "Europe/Pariss"}, clear=True)
    def test_an_unknown_timezone_fails_at_startup(self):
        """Un fuseau introuvable doit échouer au lancement, pas décaler une journée en silence."""
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn("Europe/Pariss", str(raised.exception))
        # Le cas le plus fréquent est une base de fuseaux absente : le dire évite de chercher.
        self.assertIn("tzdata", str(raised.exception))


class ArticleCharLimitTests(unittest.TestCase):
    """Le plafond d'entrée du chemin résumé, seul chemin du pipeline qui n'en avait pas."""

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_the_limit_has_a_default(self):
        self.assertEqual(DEFAULT_ARTICLE_CHAR_LIMIT, AppConfig.from_env().article_char_limit)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_ARTICLE_CHAR_LIMIT: "2500"}, clear=True)
    def test_the_limit_is_configurable(self):
        self.assertEqual(2500, AppConfig.from_env().article_char_limit)


class MailTransportTests(unittest.TestCase):
    """Le SMTP par défaut, Resend quand l'hébergeur ferme les ports SMTP."""

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_the_transport_defaults_to_smtp(self):
        self.assertEqual(MAIL_TRANSPORT_SMTP, AppConfig.from_env().mail_transport)

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, ENV_MAIL_TRANSPORT: "  ReSend  ", ENV_RESEND_API_KEY: "re_cle"},
        clear=True,
    )
    def test_the_transport_is_read_whatever_its_casing(self):
        config = AppConfig.from_env()

        self.assertEqual(MAIL_TRANSPORT_RESEND, config.mail_transport)
        self.assertEqual("re_cle", config.resend_api_key)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_MAIL_TRANSPORT: "resend "}, clear=True)
    def test_the_key_is_absent_rather_than_empty(self):
        """`is_configured()` juge la clé : une chaîne vide passerait pour une clé posée."""
        self.assertIsNone(AppConfig.from_env().resend_api_key)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_MAIL_TRANSPORT: "resnd"}, clear=True)
    def test_an_unknown_transport_fails_at_startup(self):
        """Une faute de frappe retomberait sur le SMTP, le chemin qu'on voulait éviter."""
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn(ENV_MAIL_TRANSPORT, str(raised.exception))
        self.assertIn("resnd", str(raised.exception))


class AudioModeTests(unittest.TestCase):
    """Ce que ces tests protègent : le mode décide combien de fichiers audio la journée
    produit. Une valeur fautive qu'on laisserait passer retomberait sur le mode par
    catégorie — celui qu'on voulait précisément quitter — sans que rien ne le dise."""

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_the_mode_defaults_to_one_audio_per_category(self):
        self.assertEqual(AUDIO_MODE_CATEGORY, AppConfig.from_env().audio_mode)

    @mock.patch.dict(
        os.environ, {**BASE_ENV, ENV_AUDIO_MODE: "  GloBal  "}, clear=True
    )
    def test_the_mode_is_read_whatever_its_casing(self):
        self.assertEqual(AUDIO_MODE_GLOBAL, AppConfig.from_env().audio_mode)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_AUDIO_MODE: "journee"}, clear=True)
    def test_an_unknown_mode_fails_at_startup(self):
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn(ENV_AUDIO_MODE, str(raised.exception))
        self.assertIn("journee", str(raised.exception))
        # Le message nomme ce qu'il accepte : c'est ce qui évite un second essai à l'aveugle.
        self.assertIn(AUDIO_MODE_GLOBAL, str(raised.exception))


class DebugTests(unittest.TestCase):
    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_debug_is_off_by_default(self):
        self.assertFalse(AppConfig.from_env().debug)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_DEBUG: " TRUE "}, clear=True)
    def test_debug_is_read_whatever_its_casing(self):
        self.assertTrue(AppConfig.from_env().debug)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_DEBUG: "1"}, clear=True)
    def test_only_true_turns_it_on(self):
        """Comme `SMTP_USE_TLS` : la valeur est lue, pas devinée. « 1 » n'est pas « true »,
        et un drapeau qu'on croit posé est pire qu'un drapeau absent."""
        self.assertFalse(AppConfig.from_env().debug)


if __name__ == "__main__":
    unittest.main()
