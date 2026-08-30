"""Le calendrier des fêtes : une table fixe, complète, et lisible en apposition.

Ce que ces tests protègent : la fête paraît dans la lettre tous les matins, derrière la
date. Une entrée manquante y ferait un trou, une entrée mal tournée y ferait une faute.
"""

import datetime as dt
import unittest

from rssresume.ephemeride import fetes

#: Une année bissextile, pour que le 29 février soit du parcours.
ANNEE_BISSEXTILE = 2028


def toutes_les_dates():
    debut = dt.date(ANNEE_BISSEXTILE, 1, 1)
    return [debut + dt.timedelta(days=n) for n in range(366)]


class CouvertureTests(unittest.TestCase):
    def test_every_day_of_the_year_has_a_feast(self):
        """Le 29 février compris : la table est indexée par mois et jour, pas par année."""
        manquantes = [jour.isoformat() for jour in toutes_les_dates() if not fetes.du_jour(jour)]

        self.assertEqual([], manquantes)

    def test_the_table_holds_exactly_one_entry_per_date(self):
        self.assertEqual(366, len(fetes.FETES))

    def test_a_date_outside_the_table_is_empty_not_an_error(self):
        """Chaîne vide et non `None` : la lettre perd une apposition, elle ne casse pas."""
        self.assertEqual("", fetes.FETES.get((13, 1), ""))


class RedactionTests(unittest.TestCase):
    """Chaque entrée se lit derrière « Vendredi 28 août 2026, … »."""

    #: Les débuts admis : un saint, ou une fête avec son article.
    DEBUTS = ("saint ", "sainte ", "le ", "la ", "l'", "les ", "Noël", "Notre-Dame")

    def test_every_entry_reads_as_an_apposition(self):
        for (mois, jour), fete in fetes.FETES.items():
            with self.subTest(date=f"{jour:02d}/{mois:02d}", fete=fete):
                self.assertTrue(
                    fete.startswith(self.DEBUTS),
                    f"« {fete} » ne se lit pas derrière une date",
                )

    def test_no_entry_is_capitalised_like_a_sentence(self):
        """Elle suit une virgule : « , Saint Augustin » serait une majuscule de trop."""
        for (mois, jour), fete in fetes.FETES.items():
            with self.subTest(date=f"{jour:02d}/{mois:02d}"):
                self.assertFalse(fete.startswith(("Saint ", "Sainte ", "Le ", "La ")))

    def test_no_entry_is_padded_or_punctuated(self):
        for (mois, jour), fete in fetes.FETES.items():
            with self.subTest(date=f"{jour:02d}/{mois:02d}"):
                self.assertEqual(fete, fete.strip())
                self.assertFalse(fete.endswith("."))

    def test_the_dates_are_all_plausible(self):
        for mois, jour in fetes.FETES:
            with self.subTest(date=f"{jour:02d}/{mois:02d}"):
                self.assertTrue(1 <= mois <= 12)
                self.assertTrue(1 <= jour <= 31)


class ReperesTests(unittest.TestCase):
    """Quelques dates que tout le monde peut vérifier de tête."""

    def test_the_fixed_landmarks_of_the_french_calendar(self):
        attendu = {
            (1, 1): "le Jour de l'An",
            (5, 1): "la Fête du Travail",
            (7, 14): "la Fête nationale",
            (8, 15): "l'Assomption",
            (11, 1): "la Toussaint",
            (11, 11): "l'Armistice de 1918",
            (12, 25): "Noël",
            (12, 31): "saint Sylvestre",
        }
        for (mois, jour), fete in attendu.items():
            with self.subTest(date=f"{jour:02d}/{mois:02d}"):
                self.assertEqual(fete, fetes.du_jour(dt.date(2026, mois, jour)))


if __name__ == "__main__":
    unittest.main()
