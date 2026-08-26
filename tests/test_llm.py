"""Forme des requêtes envoyées au fournisseur, selon la famille du modèle."""

import json
import unittest
from unittest import mock

from rssresume import llm

CREDENTIALS = ("https://api.example/v1", "key")
REPONSE = {"choices": [{"message": {"content": "  texte  "}, "finish_reason": "stop"}]}

CLASSIQUE = llm.ChatProfile("essai", model="gpt-4o-mini", temperature=0.4, max_tokens=512)
RAISONNANT = llm.ChatProfile(
    "essai",
    model="gpt-5.6-luna",
    temperature=0.4,
    max_tokens=512,
    reasoning_max_tokens=4096,
    effort="medium",
)


def payload_of(profile, model=None, reponse=REPONSE):
    """Lance un appel en interceptant le POST, et renvoie le payload envoyé."""
    with mock.patch.object(llm, "post", return_value=json.dumps(reponse).encode()) as post:
        llm.chat(*CREDENTIALS, profile, "système", "utilisateur", model=model)
    return post.call_args.args[3]


class FamilyDetectionTests(unittest.TestCase):
    def test_reasoning_families_are_recognized(self):
        for model in ("gpt-5-mini", "gpt-5.6-luna", "GPT-5.6-Terra", "o3-mini", "o4-mini"):
            self.assertTrue(llm.is_reasoning_model(model), model)

    def test_classic_families_are_not(self):
        for model in ("gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "", None):
            self.assertFalse(llm.is_reasoning_model(model), model)


class PayloadTests(unittest.TestCase):
    def test_a_classic_model_gets_temperature_and_max_tokens(self):
        payload = payload_of(CLASSIQUE)

        self.assertEqual(0.4, payload["temperature"])
        self.assertEqual(512, payload["max_tokens"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("max_completion_tokens", payload)

    def test_a_reasoning_model_gets_effort_and_max_completion_tokens(self):
        """`temperature` et `max_tokens` sont rejetés en 400 par ces modèles."""
        payload = payload_of(RAISONNANT)

        self.assertEqual("medium", payload["reasoning_effort"])
        self.assertEqual(4096, payload["max_completion_tokens"])
        self.assertNotIn("temperature", payload)
        self.assertNotIn("max_tokens", payload)

    def test_the_effective_model_decides_the_family(self):
        """La configuration surcharge le modèle du profil : c'est elle qui tranche."""
        self.assertIn("temperature", payload_of(RAISONNANT, model="gpt-4o-mini"))
        self.assertIn("reasoning_effort", payload_of(CLASSIQUE, model="gpt-5.6-luna"))

    def test_a_profile_without_cap_sends_none(self):
        sans_plafond = llm.ChatProfile("essai", model="gpt-5.6-luna", temperature=0.4)

        payload = payload_of(sans_plafond)

        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual("low", payload["reasoning_effort"])


class TruncationTests(unittest.TestCase):
    def test_a_truncated_answer_names_the_effective_cap(self):
        tronquee = {"choices": [{"message": {"content": "à moiti"}, "finish_reason": "length"}]}

        with self.assertRaises(llm.LLMError) as leve:
            payload_of(RAISONNANT, reponse=tronquee)

        self.assertIn("4096", str(leve.exception))
        self.assertIn("gpt-5.6-luna", str(leve.exception))


class ProfileDefaultTests(unittest.TestCase):
    def test_scoring_stays_on_a_classic_model(self):
        """Changer le modèle de notation change l'empreinte du prompt, donc renote tout."""
        self.assertFalse(llm.is_reasoning_model(llm.SCORING.model))
        # Et s'il y passait un jour, la notation est un tri sur barème, pas un raisonnement.
        self.assertEqual("none", llm.SCORING.effort)

    def test_summary_profiles_are_on_the_reasoning_model(self):
        self.assertTrue(llm.is_reasoning_model(llm.DIGEST.model))
        self.assertTrue(llm.is_reasoning_model(llm.ARTICLE_SUMMARY.model))


if __name__ == "__main__":
    unittest.main()
