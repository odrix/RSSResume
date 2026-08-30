"""L'éphéméride d'ouverture, et les trois marches sur lesquelles elle descend.

Ce que ces tests protègent : l'introduction de l'email ne doit jamais être vide, et un
modèle qui hésite ne doit jamais combler. Un fait inventé dans une lettre de veille
coûte plus cher que pas de fait du tout.
"""

import datetime as dt
import unittest

from rssresume import ephemeride
from rssresume.ephemeride import EphemerideService, fetes, histoire
from rssresume.models import Ephemeride

#: Une date de la table embarquée, et une qui n'y est pas.
CONNUE = dt.date(2026, 12, 9)  # Log4Shell
INCONNUE = dt.date(2026, 3, 3)


class FakeProvider:
    """Un fournisseur qui rend ce qu'on lui dit, ou lève ce qu'on lui dit."""

    def __init__(self, reponse=None, exception=None):
        self.reponse = reponse
        self.exception = exception
        self.appels = []

    def write_ephemeride(self, day):
        self.appels.append(day)
        if self.exception:
            raise self.exception
        return self.reponse


class SansFournisseurTests(unittest.TestCase):
    def test_a_known_date_comes_from_the_table(self):
        resultat = EphemerideService().of(CONNUE)

        self.assertEqual("table", resultat.origine)
        self.assertIn("Log4Shell", resultat.texte)

    def test_an_unknown_date_falls_back_to_the_calendar(self):
        resultat = EphemerideService().of(INCONNUE)

        self.assertEqual("calendrier", resultat.origine)
        self.assertIn("semaine", resultat.texte)

    def test_the_introduction_is_never_empty(self):
        """La dernière marche ne peut pas échouer : c'est sa seule raison d'être."""
        service = EphemerideService()
        for jour in range(366):
            resultat = service.of(dt.date(2028, 1, 1) + dt.timedelta(days=jour))
            self.assertTrue(resultat.texte.strip())


class AvecFournisseurTests(unittest.TestCase):
    def test_the_model_wins_when_it_knows_something(self):
        provider = FakeProvider("2021 — Log4Shell est rendue publique.")

        resultat = EphemerideService(provider).of(INCONNUE)

        self.assertEqual("llm", resultat.origine)
        self.assertEqual("2021 — Log4Shell est rendue publique.", resultat.texte)
        self.assertEqual([INCONNUE], provider.appels)

    def test_the_model_is_asked_once_per_sending_day_not_per_category(self):
        provider = FakeProvider("2000 — quelque chose.")
        service = EphemerideService(provider)

        service.of(CONNUE)

        self.assertEqual(1, len(provider.appels))

    def test_a_model_that_knows_nothing_hands_over_to_the_table(self):
        """« AUCUN » est une réponse attendue, pas un échec : combler serait pire."""
        for reponse in ("AUCUN", "aucun", "Aucun.", "  AUCUN  "):
            with self.subTest(reponse=reponse):
                resultat = EphemerideService(FakeProvider(reponse)).of(CONNUE)

                self.assertEqual("table", resultat.origine)
                self.assertIn("Log4Shell", resultat.texte)

    def test_an_empty_answer_hands_over_too(self):
        resultat = EphemerideService(FakeProvider("   ")).of(CONNUE)

        self.assertEqual("table", resultat.origine)

    def test_a_paragraph_is_refused(self):
        """Une éphéméride tient en deux phrases ; au-delà, ce n'est plus une ouverture."""
        resultat = EphemerideService(FakeProvider("mot " * 200)).of(CONNUE)

        self.assertEqual("table", resultat.origine)

    def test_a_provider_failure_never_costs_the_day(self):
        """Perdre scoring, résumés et synthèse vocale pour une phrase d'introduction."""
        resultat = EphemerideService(FakeProvider(exception=RuntimeError("502"))).of(CONNUE)

        self.assertEqual("table", resultat.origine)

    def test_a_provider_failure_on_an_unknown_date_still_yields_something(self):
        resultat = EphemerideService(FakeProvider(exception=RuntimeError("502"))).of(INCONNUE)

        self.assertEqual("calendrier", resultat.origine)
        self.assertTrue(resultat.texte.strip())


class FeteTests(unittest.TestCase):
    """La fête accompagne toujours l'éphéméride, quelle que soit sa source."""

    def test_the_feast_comes_along_whatever_the_source(self):
        provider = FakeProvider("2021 — quelque chose.")
        for service, attendue in ((EphemerideService(provider), "llm"), (EphemerideService(), "table")):
            with self.subTest(origine=attendue):
                resultat = service.of(CONNUE)

                self.assertEqual("saint Pierre Fourier", resultat.fete)
                self.assertEqual(CONNUE, resultat.jour)

    def test_the_calendar_fallback_still_carries_the_feast(self):
        """La table des fêtes est complète : elle n'a aucune marche à descendre."""
        resultat = EphemerideService().of(INCONNUE)

        self.assertEqual("calendrier", resultat.origine)
        self.assertEqual(fetes.du_jour(INCONNUE), resultat.fete)
        self.assertTrue(resultat.fete)


class PourEnvoiTests(unittest.TestCase):
    """Ce qu'un renvoi met en ouverture, sans rappeler le moindre modèle."""

    def test_an_ephemeride_of_today_is_reused_as_is(self):
        deja = Ephemeride(jour=CONNUE, fete="x", texte="déjà payée", origine="llm")

        self.assertIs(deja, ephemeride.pour_envoi(deja, CONNUE))

    def test_an_ephemeride_of_another_day_is_replaced(self):
        """Elle daterait la lettre du mauvais jour et annoncerait la fête d'un autre."""
        vieille = Ephemeride(jour=INCONNUE, fete="x", texte="d'un autre jour", origine="llm")

        resultat = ephemeride.pour_envoi(vieille, CONNUE)

        self.assertEqual(CONNUE, resultat.jour)
        self.assertNotIn("d'un autre jour", resultat.texte)
        self.assertIn("Log4Shell", resultat.texte)

    def test_nothing_reread_still_yields_an_opening(self):
        resultat = ephemeride.pour_envoi(None, INCONNUE)

        self.assertEqual(INCONNUE, resultat.jour)
        self.assertTrue(resultat.fete)
        self.assertTrue(resultat.texte)


class CalendrierTests(unittest.TestCase):
    def test_the_calendar_counts_the_days(self):
        resultat = ephemeride.calendrier(dt.date(2026, 1, 1))

        self.assertIn("1er jour de l'année", resultat.texte)
        self.assertIn("364 jours", resultat.texte)

    def test_the_last_day_of_the_year_is_singular_free(self):
        resultat = ephemeride.calendrier(dt.date(2026, 12, 31))

        self.assertIn("0 jour avant", resultat.texte)


class TableTests(unittest.TestCase):
    def test_every_entry_is_dated_and_readable(self):
        """Une entrée sans année ou réduite à trois mots n'a rien à faire en ouverture."""
        for (mois, jour), texte in histoire.EVENEMENTS.items():
            with self.subTest(date=f"{jour:02d}/{mois:02d}"):
                self.assertTrue(1 <= mois <= 12)
                self.assertTrue(1 <= jour <= 31)
                self.assertRegex(texte, r"^(19|20)\d{2} — ")
                self.assertGreater(len(texte), 40)
                self.assertLess(len(texte), ephemeride.LONGUEUR_MAX)


if __name__ == "__main__":
    unittest.main()
