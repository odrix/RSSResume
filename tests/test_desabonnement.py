"""Le jeton du lien de désabonnement : signé, relu, et lié aux destinataires.

Ce que ces tests protègent : un lien qu'on ne peut ni forger ni détourner, qui se
recalcule à l'identique — `--send-only` doit rendre la même lettre — et qui cesse de
valoir dès que les destinataires qu'il désigne ont changé.
"""

import unittest

from rssresume.desabonnement import (
    LONGUEUR_EMPREINTE_ADRESSE,
    OBJET_DESABONNEMENT,
    Desabonnement,
    JetonInvalide,
    Signataire,
)

SECRET = "s" * 48
PROFIL_ID = "0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71"
EMAILS = ["a@example.com", "b@example.com"]


def desabonnement(secret=SECRET, objet=OBJET_DESABONNEMENT):
    return Desabonnement(Signataire(secret, objet))


class SignataireTests(unittest.TestCase):
    def test_signed_fields_are_read_back(self):
        signataire = Signataire(SECRET, "essai")

        self.assertEqual(["v1", "abc", "d-e_f"], signataire.verifier(signataire.signer("v1", "abc", "d-e_f")))

    def test_an_altered_token_is_refused(self):
        signataire = Signataire(SECRET, "essai")
        jeton = signataire.signer("v1", "abc")
        corps, _, signature = jeton.rpartition(".")
        for altere in (
            corps.replace("abc", "abd") + "." + signature,
            corps + "." + signature[:-1] + ("A" if signature[-1] != "A" else "B"),
            corps,
            "",
            "." + signature,
            jeton + ".",
        ):
            with self.subTest(altere=altere), self.assertRaises(JetonInvalide):
                signataire.verifier(altere)

    def test_another_secret_or_another_use_does_not_verify(self):
        """Une clé par usage : un jeton détourné vers un autre lien signé n'y vaut rien."""
        jeton = Signataire(SECRET, "essai").signer("v1", "abc")
        for autre in (Signataire("t" * 48, "essai"), Signataire(SECRET, "autre-usage")):
            with self.subTest(), self.assertRaises(JetonInvalide):
                autre.verifier(jeton)

    def test_a_field_outside_the_url_alphabet_cannot_be_signed(self):
        for champ in ("a.b", "a/b", "", "é"):
            with self.subTest(champ=champ), self.assertRaises(ValueError):
                Signataire(SECRET, "essai").signer(champ)

    def test_an_empty_secret_is_refused(self):
        with self.assertRaises(ValueError):
            Signataire("", "essai")


class DesabonnementTests(unittest.TestCase):
    def test_the_token_is_read_back_into_its_profile(self):
        service = desabonnement()

        demande = service.lire(service.jeton(PROFIL_ID, EMAILS))

        self.assertEqual(PROFIL_ID, demande.profil_id)
        self.assertTrue(demande.concerne(EMAILS))

    def test_the_token_is_deterministic(self):
        """Recalculé à l'identique : c'est ce qui permet à `--send-only` de rendre la même lettre."""
        self.assertEqual(
            desabonnement().jeton(PROFIL_ID, EMAILS), desabonnement().jeton(PROFIL_ID, EMAILS)
        )

    def test_the_fingerprints_ignore_case_and_order(self):
        service = desabonnement()
        demande = service.lire(service.jeton(PROFIL_ID, EMAILS))

        self.assertTrue(demande.concerne(["B@Example.com"]))
        self.assertEqual(
            service.jeton(PROFIL_ID, EMAILS), service.jeton(PROFIL_ID, ["B@EXAMPLE.COM", " a@example.com"])
        )

    def test_the_token_carries_one_short_fingerprint_per_address(self):
        _, _, empreintes, _ = desabonnement().jeton(PROFIL_ID, [*EMAILS, "A@example.com"]).split(".")

        self.assertEqual(2 * LONGUEUR_EMPREINTE_ADRESSE, len(empreintes))

    def test_a_list_grown_after_sending_keeps_the_link(self):
        """La liste vit après l'envoi : une invitation confirmée ne tue pas le lien des lettres parties."""
        service = desabonnement()
        demande = service.lire(service.jeton(PROFIL_ID, EMAILS))

        self.assertTrue(demande.concerne([*EMAILS, "c@example.com"]))

    def test_one_address_of_the_letter_still_there_is_enough(self):
        service = desabonnement()
        demande = service.lire(service.jeton(PROFIL_ID, EMAILS))

        self.assertTrue(demande.concerne(["a@example.com", "c@example.com"]))

    def test_without_any_address_of_the_letter_the_link_is_refused(self):
        """Vidés, ou remplacés, les destinataires ne correspondent plus : le lien ne sert qu'une fois."""
        service = desabonnement()
        demande = service.lire(service.jeton(PROFIL_ID, EMAILS))

        self.assertFalse(demande.concerne([]))
        self.assertFalse(demande.concerne(["c@example.com", "d@example.com"]))

    def test_a_token_without_recipient_cannot_be_made(self):
        with self.assertRaises(ValueError):
            desabonnement().jeton(PROFIL_ID, [])

    def test_the_recipients_do_not_appear_in_the_token(self):
        jeton = desabonnement().jeton(PROFIL_ID, EMAILS)

        self.assertNotIn("example", jeton)

    def test_a_token_from_another_key_is_refused(self):
        jeton = desabonnement(secret="t" * 48).jeton(PROFIL_ID, EMAILS)

        with self.assertRaises(JetonInvalide):
            desabonnement().lire(jeton)

    def test_a_token_of_another_format_is_refused(self):
        signataire = Signataire(SECRET, OBJET_DESABONNEMENT)
        for jeton in (signataire.signer("v2", PROFIL_ID, "x"), signataire.signer("v1", PROFIL_ID)):
            with self.subTest(jeton=jeton), self.assertRaises(JetonInvalide):
                Desabonnement(signataire).lire(jeton)

    def test_the_link_points_to_the_site_page(self):
        self.assertEqual(
            "https://veille.example.com/desabonnement/abc",
            Desabonnement.lien("https://veille.example.com/", "abc"),
        )


if __name__ == "__main__":
    unittest.main()
