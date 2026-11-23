"""Le lien de vote d'une journée, et la saisie d'un retour.

Ce que ces tests protègent : un lien ne vaut que pour son profil et sa journée, on ne peut
ni le forger ni le détourner d'un autre lien signé, il se recalcule à l'identique pour
`--send-only` ; et un retour refuse ce qui n'est pas un avis connu ou un commentaire trop
long, en nommant le champ fautif.
"""

import datetime as dt
import unittest

from rssresume.desabonnement import OBJET_DESABONNEMENT, Desabonnement, JetonInvalide, Signataire
from rssresume.profil import ChampInvalide
from rssresume.retours import (
    LONGUEUR_MAX_COMMENTAIRE,
    OBJET_RETOUR,
    Avis,
    JourneeVisee,
    LienRetour,
    Retour,
)

SECRET = "s" * 48
PROFIL_ID = "0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71"
AUTRE_ID = "7c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f"
JOUR = dt.date(2026, 11, 22)


def lien_retour(secret=SECRET, objet=OBJET_RETOUR):
    return LienRetour(Signataire(secret, objet))


class LienRetourTests(unittest.TestCase):
    def test_the_token_is_read_back_into_its_profile_and_day(self):
        service = lien_retour()

        self.assertEqual(JourneeVisee(PROFIL_ID, JOUR), service.lire(service.jeton(PROFIL_ID, JOUR)))

    def test_the_token_is_deterministic(self):
        """Recalculé à l'identique : c'est ce qui permet à `--send-only` de rendre la même lettre."""
        self.assertEqual(lien_retour().jeton(PROFIL_ID, JOUR), lien_retour().jeton(PROFIL_ID, JOUR))

    def test_another_profile_or_another_day_gives_another_token(self):
        service = lien_retour()
        jeton = service.jeton(PROFIL_ID, JOUR)

        self.assertNotEqual(jeton, service.jeton(AUTRE_ID, JOUR))
        self.assertNotEqual(jeton, service.jeton(PROFIL_ID, JOUR + dt.timedelta(days=1)))

    def test_an_altered_field_is_refused(self):
        """Changer le profil ou la date d'un jeton en garde la signature, qui ne correspond plus."""
        service = lien_retour()
        jeton = service.jeton(PROFIL_ID, JOUR)
        for altere in (
            jeton.replace(PROFIL_ID, AUTRE_ID),
            jeton.replace(JOUR.isoformat(), "2026-11-23"),
            jeton[:-1] + ("A" if jeton[-1] != "A" else "B"),
            jeton.rsplit(".", 1)[0],
            "",
        ):
            with self.subTest(altere=altere), self.assertRaises(JetonInvalide):
                service.lire(altere)

    def test_a_token_from_another_secret_is_refused(self):
        with self.assertRaises(JetonInvalide):
            lien_retour().lire(lien_retour(secret="t" * 48).jeton(PROFIL_ID, JOUR))

    def test_an_unsubscribe_token_is_never_a_vote_token(self):
        """Même secret, autre usage : un jeton de désabonnement n'ouvre pas le vote, ni l'inverse."""
        desabonnement = Desabonnement(Signataire(SECRET, OBJET_DESABONNEMENT))
        with self.assertRaises(JetonInvalide):
            lien_retour().lire(desabonnement.jeton(PROFIL_ID, ["a@example.com"]))
        with self.assertRaises(JetonInvalide):
            desabonnement.lire(lien_retour().jeton(PROFIL_ID, JOUR))
        # Signé avec la clé du désabonnement mais à la forme d'un vote : refusé aussi.
        with self.assertRaises(JetonInvalide):
            lien_retour().lire(lien_retour(objet=OBJET_DESABONNEMENT).jeton(PROFIL_ID, JOUR))

    def test_a_token_of_another_format_is_refused(self):
        signataire = Signataire(SECRET, OBJET_RETOUR)
        for jeton in (
            signataire.signer("v2", PROFIL_ID, JOUR.isoformat()),
            signataire.signer("v1", PROFIL_ID),
            signataire.signer("v1", PROFIL_ID, JOUR.isoformat(), "x"),
        ):
            with self.subTest(jeton=jeton), self.assertRaises(JetonInvalide):
                LienRetour(signataire).lire(jeton)

    def test_an_impossible_date_is_refused_even_when_signed(self):
        signataire = Signataire(SECRET, OBJET_RETOUR)
        for date in ("2026-02-30", "20261122", "hier"):
            with self.subTest(date=date), self.assertRaises(JetonInvalide):
                LienRetour(signataire).lire(signataire.signer("v1", PROFIL_ID, date))

    def test_the_link_carries_the_opinion_in_clear(self):
        self.assertEqual(
            "https://veille.example.com/retour/abc?avis=pas_utile",
            LienRetour.lien("https://veille.example.com/", "abc", Avis.PAS_UTILE),
        )
        self.assertEqual(["Utile", "Pas utile"], [avis.libelle for avis in Avis])


class RetourSaisiTests(unittest.TestCase):
    def test_a_vote_is_read_with_its_comment(self):
        retour = Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": "  Bien.\r\nMerci  "})

        self.assertEqual((PROFIL_ID, JOUR, Avis.UTILE, "Bien.\nMerci"), (
            retour.profil_id, retour.jour, retour.avis, retour.commentaire
        ))

    def test_the_comment_is_optional(self):
        for saisie in ({"avis": "pas_utile"}, {"avis": "pas_utile", "commentaire": None}):
            with self.subTest(saisie=saisie):
                self.assertEqual("", Retour.saisi(PROFIL_ID, JOUR, saisie).commentaire)

    def test_the_comment_is_bounded_and_refused_beyond(self):
        """Refusé et non tronqué : couper la fin d'un texte sans le dire en perd la conclusion."""
        juste = "é" * LONGUEUR_MAX_COMMENTAIRE
        self.assertEqual(juste, Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": juste}).commentaire)
        # Compté en points de code : 2 000 emojis passent, comme sur le site.
        emojis = "\N{THUMBS UP SIGN}" * LONGUEUR_MAX_COMMENTAIRE
        self.assertEqual(emojis, Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": emojis}).commentaire)

        with self.assertRaises(ChampInvalide) as refus:
            Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": juste + "x"})
        self.assertEqual("commentaire", refus.exception.champ)

    def test_a_crlf_counts_as_one_character(self):
        commentaire = "a\r\n" * (LONGUEUR_MAX_COMMENTAIRE // 2)

        retour = Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": commentaire})

        self.assertLessEqual(len(retour.commentaire), LONGUEUR_MAX_COMMENTAIRE)

    def test_an_unknown_opinion_names_its_field(self):
        for avis in (None, "", "UTILE", "moyen", 1):
            with self.subTest(avis=avis), self.assertRaises(ChampInvalide) as refus:
                Retour.saisi(PROFIL_ID, JOUR, {"avis": avis})
            self.assertEqual("avis", refus.exception.champ)

    def test_a_comment_that_is_not_text_names_its_field(self):
        with self.assertRaises(ChampInvalide) as refus:
            Retour.saisi(PROFIL_ID, JOUR, {"avis": "utile", "commentaire": ["x"]})
        self.assertEqual("commentaire", refus.exception.champ)

    def test_a_body_that_is_not_an_object_is_refused(self):
        with self.assertRaises(ValueError):
            Retour.saisi(PROFIL_ID, JOUR, ["utile"])

    def test_the_json_form(self):
        retour = Retour(PROFIL_ID, JOUR, Avis.PAS_UTILE, "Trop long.", "2026-11-23T07:00:00+00:00", "bea")

        self.assertEqual(
            {
                "username": "bea",
                "jour": "2026-11-22",
                "avis": "pas_utile",
                "commentaire": "Trop long.",
                "vote_le": "2026-11-23T07:00:00+00:00",
            },
            retour.en_json(),
        )


if __name__ == "__main__":
    unittest.main()
