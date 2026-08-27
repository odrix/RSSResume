"""La règle de sélection d'une catégorie : seuil, seuil de repli, minimum, plafond.

L'objet est testé seul, sans pipeline : c'est lui qui décide qui entre dans un digest,
et `test_scoring_pipeline.py` vérifie ensuite qu'il est bien branché.
"""

import unittest

from rssresume.models import SelectionRule

#: Les réglages de production : seuil 7, repli à 5 en dessous de cinq articles retenus.
REGLE = SelectionRule(seuil=7, seuil_repli=5, minimum=5, plafond=12)


def appliquer(regle, *scores):
    """Applique la règle à une journée décrite par ses seuls scores."""
    return regle.appliquer(list(scores), lambda score: score)


class SeuilDuJourTests(unittest.TestCase):
    def test_the_normal_threshold_holds_when_it_retains_enough(self):
        selection = appliquer(REGLE, 10, 9, 8, 7, 7, 6, 5)

        self.assertEqual(7, selection.seuil)
        self.assertFalse(selection.repliee)
        self.assertEqual([10, 9, 8, 7, 7], selection.retenus)

    def test_a_thin_day_falls_back_to_the_lower_threshold(self):
        """Quatre articles au-dessus de sept : le seuil du jour tombe à cinq."""
        selection = appliquer(REGLE, 9, 8, 7, 7, 6, 5, 4)

        self.assertEqual(5, selection.seuil)
        self.assertTrue(selection.repliee)
        self.assertEqual([9, 8, 7, 7, 6, 5], selection.retenus)

    def test_the_fallback_lowers_the_threshold_it_does_not_top_up(self):
        """Le repli abaisse le seuil pour tout le monde : la journée peut dépasser le minimum."""
        selection = appliquer(REGLE, 9, 6, 6, 6, 6, 6, 6, 6)

        self.assertEqual(8, len(selection.retenus))

    def test_the_cap_still_bounds_a_fallen_back_day(self):
        petite = SelectionRule(seuil=7, seuil_repli=5, minimum=5, plafond=3)

        selection = appliquer(petite, 9, 6, 6, 6, 6, 6)

        self.assertEqual([9, 6, 6], selection.retenus)

    def test_the_fallback_cannot_raise_the_threshold(self):
        """Une catégorie déjà à cinq n'a rien à replier : le repli n'y fait jamais rien."""
        generaliste = SelectionRule(seuil=5, seuil_repli=7, minimum=5, plafond=12)

        selection = appliquer(generaliste, 6, 5, 5)

        self.assertEqual(5, selection.seuil)
        self.assertFalse(selection.repliee)
        self.assertEqual([6, 5, 5], selection.retenus)

    def test_a_minimum_of_zero_disables_the_fallback(self):
        sans_repli = SelectionRule(seuil=7, seuil_repli=5, minimum=0, plafond=12)

        selection = appliquer(sans_repli, 9, 6, 5)

        self.assertEqual(7, selection.seuil)
        self.assertEqual([9], selection.retenus)

    def test_an_empty_day_reports_the_fallback_threshold(self):
        """Zéro article retenu est bien en dessous du minimum : le seuil rapporté est le repli."""
        selection = appliquer(REGLE)

        self.assertEqual(5, selection.seuil)
        self.assertEqual([], selection.retenus)


if __name__ == "__main__":
    unittest.main()
