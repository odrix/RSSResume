"""Grille de tarifs : correspondance des modèles et calcul du coût."""

import json
import unittest
from unittest import mock

from rssresume import pricing


class TarifTests(unittest.TestCase):
    def test_an_exact_model_name_is_found(self):
        self.assertEqual({"input": 0.15, "output": 0.60}, pricing.tarif("gpt-4o-mini"))

    def test_a_dated_snapshot_falls_back_on_its_family(self):
        """Lister toutes les dates de publication serait intenable."""
        for date in ("gpt-4o-mini-2024-07-18", "gpt-4o-mini-0613"):
            self.assertEqual(pricing.tarif("gpt-4o-mini"), pricing.tarif(date), date)

    def test_the_longest_matching_family_wins(self):
        """`gpt-4o-mini` commence par `gpt-4o` : c'est le plus précis qui doit trancher."""
        self.assertEqual(pricing.tarif("gpt-4o-mini"), pricing.tarif("gpt-4o-mini-2024-07-18"))
        self.assertNotEqual(pricing.tarif("gpt-4o"), pricing.tarif("gpt-4o-mini-2024-07-18"))

    def test_a_neighbour_model_is_not_priced_as_its_prefix(self):
        """`gpt-5.6-luna` commence par `gpt-5` sans en être une version datée.

        Le facturer au tarif de `gpt-5` rendrait un coût faux et vraisemblable, que
        rien ne signalerait — pire qu'un coût absent.
        """
        for modele in ("gpt-5.6-luna", "gpt-5-turbo-inconnu", "gpt-4o-maison"):
            self.assertIsNone(pricing.tarif(modele), modele)

    def test_an_unknown_model_has_no_tarif(self):
        self.assertIsNone(pricing.tarif("modele-jamais-vu"))
        self.assertIsNone(pricing.tarif(""))
        self.assertIsNone(pricing.tarif(None))


class CostTests(unittest.TestCase):
    def test_token_pricing_counts_input_and_output_separately(self):
        # 1 M en entrée à 0,15 $ + 1 M en sortie à 0,60 $
        self.assertAlmostEqual(0.75, pricing.cost("gpt-4o-mini", 1_000_000, 1_000_000))

    def test_character_pricing_ignores_tokens(self):
        """La synthèse vocale historique est facturée au caractère, pas au token."""
        self.assertAlmostEqual(0.015, pricing.cost("tts-1", input_tokens=9999, characters=1000))

    def test_an_unknown_model_costs_none_rather_than_zero(self):
        """Un coût inconnu rendu à zéro se lirait comme un appel gratuit."""
        self.assertIsNone(pricing.cost("modele-jamais-vu", 1000, 1000))

    def test_a_tarif_without_output_bills_the_input_only(self):
        self.assertAlmostEqual(0.60, pricing.cost("gpt-4o-mini-tts", 1_000_000, 1_000_000))


class OverrideTests(unittest.TestCase):
    def test_the_environment_completes_the_table(self):
        prix = json.dumps({"modele-maison": {"input": 1.0, "output": 2.0}})

        with mock.patch.dict("os.environ", {pricing.PRICES_ENV: prix}):
            self.assertAlmostEqual(3.0, pricing.cost("modele-maison", 1_000_000, 1_000_000))

    def test_the_environment_overrides_a_known_model(self):
        prix = json.dumps({"gpt-4o-mini": {"input": 0.0, "output": 0.0}})

        with mock.patch.dict("os.environ", {pricing.PRICES_ENV: prix}):
            self.assertAlmostEqual(0.0, pricing.cost("gpt-4o-mini", 1_000_000, 1_000_000))

    def test_an_unreadable_override_does_not_break_the_run(self):
        """Un JSON de configuration cassé ne doit pas faire échouer une veille."""
        with mock.patch.dict("os.environ", {pricing.PRICES_ENV: "{pas du json"}):
            self.assertAlmostEqual(0.00045, pricing.cost("gpt-4o-mini", 1000, 500))


if __name__ == "__main__":
    unittest.main()
