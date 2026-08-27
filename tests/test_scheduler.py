"""Le passage quotidien : l'heure lue, le prochain réveil, la journée digérée."""

import datetime as dt
import unittest
import zoneinfo

from rssresume.tools import console
from rssresume.scheduler import (
    DEFAULT_DAYS_BACK,
    DEFAULT_SCHEDULE,
    DailySchedule,
    parse_days_back,
    parse_schedule,
    run_forever,
)

# La boucle trace chaque passage : les tests n'ont pas à l'afficher.
console.enable(False)

PARIS = zoneinfo.ZoneInfo("Europe/Paris")


def schedule(heure="07:00", days_back=DEFAULT_DAYS_BACK):
    return DailySchedule(parse_schedule(heure), PARIS, days_back)


def paris(texte):
    return dt.datetime.fromisoformat(texte).replace(tzinfo=PARIS)


class ParseTests(unittest.TestCase):
    def test_defaults_to_seven(self):
        self.assertEqual(dt.time.fromisoformat(DEFAULT_SCHEDULE), parse_schedule(None))
        self.assertEqual(dt.time.fromisoformat(DEFAULT_SCHEDULE), parse_schedule("   "))

    def test_reads_an_hour(self):
        self.assertEqual(dt.time(6, 30), parse_schedule(" 06:30 "))

    def test_rejects_nonsense(self):
        # Ignorée en silence, une heure mal écrite ne se verrait qu'au premier matin sans digest.
        with self.assertRaises(ValueError):
            parse_schedule("7h")

    def test_rejects_a_timezone(self):
        with self.assertRaises(ValueError):
            parse_schedule("07:00+02:00")

    def test_days_back(self):
        self.assertEqual(DEFAULT_DAYS_BACK, parse_days_back(None))
        self.assertEqual(0, parse_days_back("0"))
        with self.assertRaises(ValueError):
            parse_days_back("-1")


class NextRunTests(unittest.TestCase):
    def test_today_when_the_hour_is_still_ahead(self):
        self.assertEqual(paris("2026-08-24 07:00"), schedule().next_run(paris("2026-08-24 03:12")))

    def test_tomorrow_once_it_has_passed(self):
        self.assertEqual(paris("2026-08-25 07:00"), schedule().next_run(paris("2026-08-24 07:00")))

    def test_reads_the_clock_in_the_configured_timezone(self):
        # 05:30 UTC, soit 07:30 à Paris en heure d'été : le passage du jour est passé.
        moment = dt.datetime(2026, 8, 24, 5, 30, tzinfo=dt.timezone.utc)

        self.assertEqual(paris("2026-08-25 07:00"), schedule().next_run(moment))


class TargetDayTests(unittest.TestCase):
    def test_yesterday_by_default(self):
        # Un passage à 7 h qui digérerait « aujourd'hui » ne lirait que minuit à 7 h.
        self.assertEqual(dt.date(2026, 8, 23), schedule().target_day(paris("2026-08-24 07:00")))

    def test_the_day_itself_when_asked(self):
        self.assertEqual(
            dt.date(2026, 8, 24), schedule(days_back=0).target_day(paris("2026-08-24 07:00"))
        )


class RunForeverTests(unittest.TestCase):
    def setUp(self):
        self.attentes = []
        self.appels = []

    def attendre(self, secondes, arret=False):
        self.attentes.append(secondes)
        return arret

    def run_two(self, run, depart="2026-08-24 03:00"):
        return run_forever(
            schedule(),
            run=run,
            attendre=self.attendre,
            maintenant=lambda: paris(depart),
            passages=2,
        )

    def test_runs_each_day_on_its_own_date(self):
        self.run_two(self.appels.append)

        self.assertEqual([["--date", "2026-08-23"], ["--date", "2026-08-24"]], self.appels)

    def test_sleeps_until_the_next_run(self):
        self.run_two(self.appels.append)

        # 03:00 → 07:00 le jour même, puis 03:00 → 07:00 le lendemain (l'horloge est figée).
        self.assertEqual([4 * 3600, 28 * 3600], self.attentes)

    def test_a_failed_day_does_not_stop_the_loop(self):
        def run(argv):
            self.appels.append(argv)
            raise RuntimeError("FreshRSS injoignable")

        self.assertEqual(0, self.run_two(run))
        self.assertEqual(2, len(self.appels))

    def test_stops_on_signal(self):
        code = run_forever(
            schedule(),
            run=self.appels.append,
            attendre=lambda secondes: self.attendre(secondes, arret=True),
            maintenant=lambda: paris("2026-08-24 03:00"),
        )

        self.assertEqual(0, code)
        self.assertEqual([], self.appels)


if __name__ == "__main__":
    unittest.main()
