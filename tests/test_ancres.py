"""Poser les liens des articles dans le texte du résumé.

Ce que ces tests protègent : un lien mal posé est pire que pas de lien. Il mène à un
article qui n'est pas celui dont la phrase parle, et rien ne le signale au lecteur —
alors qu'un article non ancré reste, lui, dans la liste « À lire ».
"""

import unittest

from rssresume import ancres
from rssresume.models import Link


def lien(titre, url="https://exemple.test/a"):
    return Link(title=titre, source="Flux", url=url)


def rendu(texte, liens):
    """Le découpage rejoué à plat, les ancres entre crochets, pour lire l'attribution."""
    return "".join(
        f"[{segment.texte}]({segment.url})" if segment.url else segment.texte
        for segment in ancres.ancrer(texte, liens)
    )


class AncresDuTitreTests(unittest.TestCase):
    def test_the_longest_group_comes_first(self):
        trouvees = ancres.ancres_du_titre("CISA orders feds to patch Citrix NetScaler flaw")

        self.assertEqual("Citrix NetScaler", trouvees[0])
        self.assertIn("NetScaler", trouvees)
        self.assertIn("CISA", trouvees)

    def test_common_words_are_never_anchors(self):
        """La casse de titre anglaise met une majuscule partout : elle ne prouve rien."""
        trouvees = ancres.ancres_du_titre("The New Flaw That Everyone Should Patch Now")

        self.assertNotIn("The", trouvees)
        self.assertNotIn("New", trouvees)
        self.assertNotIn("Now", trouvees)

    def test_generic_security_acronyms_are_refused(self):
        """« RCE » nomme une classe de problème, jamais un article."""
        trouvees = ancres.ancres_du_titre("Next.js patch fixes an unauthenticated RCE")

        self.assertIn("Next.js", trouvees)
        self.assertNotIn("RCE", trouvees)

    def test_a_full_vulnerability_identifier_is_a_prime_anchor(self):
        """Il porte des chiffres, ne ressemble à rien d'autre, et désigne exactement un sujet."""
        trouvees = ancres.ancres_du_titre("Log4Shell (CVE-2021-44228) touche presque tout")

        self.assertIn("CVE-2021-44228", trouvees)
        self.assertIn("Log4Shell", trouvees)

    def test_the_french_elision_does_not_swallow_the_proper_noun(self):
        """« 700 agents d'OpenAI » : sans traitement, « d'OpenAI » passe pour un mot banal."""
        self.assertIn("OpenAI", ancres.ancres_du_titre("Les 700 agents d'OpenAI en question"))
        self.assertIn("ANSSI", ancres.ancres_du_titre("Le référentiel de l'ANSSI évolue"))

    def test_a_short_lowercase_word_is_too_vague_to_anchor(self):
        trouvees = ancres.ancres_du_titre("Ring et AWS")

        self.assertIn("Ring", trouvees)
        self.assertIn("AWS", trouvees)

    def test_a_title_without_any_proper_noun_yields_nothing(self):
        self.assertEqual([], ancres.ancres_du_titre("une faille dans un logiciel courant"))


class PlacementTests(unittest.TestCase):
    def test_a_link_lands_on_the_word_that_recalls_its_title(self):
        resultat = rendu(
            "Une faille critique touche Traefik.", [lien("Multiples vulnérabilités dans Traefik")]
        )

        self.assertEqual("Une faille critique touche [Traefik](https://exemple.test/a).", resultat)

    def test_the_summary_text_itself_is_never_altered(self):
        """La voix lit le même texte : l'ancrage est un appariement, pas une réécriture."""
        texte = "Une faille critique touche Traefik, et c'est urgent."
        segments = ancres.ancrer(texte, [lien("Faille dans Traefik")])

        self.assertEqual(texte, "".join(segment.texte for segment in segments))

    def test_an_article_is_anchored_once_and_only_once(self):
        resultat = rendu(
            "Traefik est touché. Traefik doit être corrigé.", [lien("Faille dans Traefik")]
        )

        self.assertEqual(1, resultat.count("https://exemple.test/a"))

    def test_the_best_anchor_wins_even_when_it_comes_later_in_the_text(self):
        """Placé paragraphe par paragraphe, l'article se serait posé sur le sigle du premier."""
        liens = [lien("Next.js corrige une RCE non authentifiée", "https://exemple.test/next")]
        texte = (
            "Une RCE est signalée sur un autre produit.\n\n"
            "Enfin, Next.js publie un correctif critique."
        )

        resultat = rendu(texte, liens)

        self.assertIn("[Next.js](https://exemple.test/next)", resultat)
        self.assertNotIn("[RCE]", resultat)

    def test_a_longer_anchor_reserves_its_place_before_a_single_word(self):
        liens = [
            lien("CISA adds flaws including NetScaler and SQL Server", "https://exemple.test/kev"),
            lien("Patch the Citrix NetScaler flaw now", "https://exemple.test/net"),
        ]

        resultat = rendu("Au menu : NetScaler, Linux et SQL Server.", liens)

        self.assertIn("[SQL Server](https://exemple.test/kev)", resultat)
        self.assertIn("[NetScaler](https://exemple.test/net)", resultat)

    def test_two_articles_after_the_same_word_do_not_overlap(self):
        liens = [
            lien("Traefik corrigé", "https://exemple.test/1"),
            lien("Traefik toujours exposé", "https://exemple.test/2"),
        ]

        resultat = rendu("Une seule mention de Traefik ici.", liens)

        self.assertEqual(1, resultat.count("[Traefik]"))
        self.assertIn("https://exemple.test/1", resultat)
        self.assertNotIn("https://exemple.test/2", resultat)

    def test_an_article_the_summary_never_names_stays_unanchored(self):
        """Il n'est pas perdu pour autant : la liste « À lire » ne rate personne."""
        resultat = rendu("Le résumé ne cite personne.", [lien("Faille dans Traefik")])

        self.assertEqual("Le résumé ne cite personne.", resultat)

    def test_case_matters_because_proper_nouns_are_what_we_look_for(self):
        resultat = rendu("On a passé un anneau au doigt.", [lien("Ring chiffre ses vidéos")])

        self.assertNotIn("[", resultat)

    def test_an_anchor_never_matches_inside_a_longer_word(self):
        resultat = rendu("Le mot Traefikeur n'existe pas.", [lien("Faille dans Traefik")])

        self.assertNotIn("[", resultat)

    def test_an_anchor_may_span_a_line_break(self):
        """Le titre sépare ses mots d'une espace ; le résumé peut passer à la ligne."""
        resultat = rendu("Voici SQL\nServer aujourd'hui.", [lien("Le cas SQL Server")])

        self.assertIn("[SQL\nServer]", resultat)

    def test_no_anchor_ever_straddles_a_paragraph_break(self):
        """Un lien à cheval sur deux `<p>` ne se refermerait dans aucun des deux.

        L'article n'y perd pas son ancre pour autant : il se rabat sur un mot seul, à
        l'intérieur d'un paragraphe.
        """
        segments = ancres.ancrer("Voici SQL\n\nServer aujourd'hui.", [lien("Le cas SQL Server")])

        portant = [segment for segment in segments if segment.url]
        self.assertTrue(portant)
        for segment in portant:
            self.assertNotIn("\n\n", segment.texte)

    def test_no_link_no_work(self):
        segments = ancres.ancrer("Un texte sans lien.", [])

        self.assertEqual([ancres.Segment("Un texte sans lien.")], segments)


if __name__ == "__main__":
    unittest.main()
