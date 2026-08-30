"""Le tri déterministe des avis CERT-FR : appariement, criticité, phrase, chargement.

Ce que ces tests protègent tient en deux phrases. Un avis mal apparié fait ouvrir un
ticket sur un composant qu'on n'exploite pas, et à la troisième fois plus personne ne
lit la phrase du matin. Un avis manqué, lui, ne se remarque que le jour où il est trop
tard — d'où l'attention portée aux deux extrémités : les faux positifs d'un nom court,
et le composant que seul le corps de l'avis nomme.
"""

import datetime as dt
import unittest

from rssresume import certfr
from rssresume.models import Article

JOUR = dt.datetime(2026, 8, 28, 6, 0, tzinfo=dt.timezone.utc)


def avis(titre, contenu="", item_id="avis-1"):
    """Un avis tel que le flux « CERT-FR - Avis de securite » le rend.

    Titre stéréotypé et description d'une phrase : c'est tout ce que le flux publie, et
    c'est donc tout ce sur quoi l'appariement peut travailler.
    """
    return Article(
        item_id=item_id,
        category="1 - Alertes et avis CERT-FR ANSSI",
        title=titre,
        url=f"https://www.cert.ssi.gouv.fr/avis/{item_id}/",
        published_at=JOUR,
        feed_title="CERT-FR - Avis de securite",
        content_text=contenu,
    )


def stack(composants):
    """Une stack montée à la main : {nom canonique: [alias]}."""
    return certfr.Stack(
        certfr.Composant(nom, alias) for nom, alias in composants.items()
    )


def service(composants):
    return certfr.CertfrService(stack(composants))


class AppariementTests(unittest.TestCase):
    def test_a_component_named_in_the_title_is_matched(self):
        revue = service({"Keycloak": []}).lire(
            [avis("Multiples vulnérabilités dans Keycloak (25 août 2026)")]
        )

        self.assertEqual(["Keycloak"], list(revue.avis[0].composants))

    def test_a_component_named_only_in_the_body_is_matched(self):
        """« Multiples vulnérabilités dans les produits IBM » ne nomme rien dans son titre."""
        revue = service({"IBM MQ": []}).lire(
            [
                avis(
                    "Multiples vulnérabilités dans les produits IBM (28 août 2026)",
                    "De multiples vulnérabilités ont été découvertes dans IBM MQ.",
                )
            ]
        )

        self.assertEqual(["IBM MQ"], list(revue.avis[0].composants))

    def test_matching_ignores_case_and_accents(self):
        """Le libellé déclaré et le texte de l'avis ne s'écrivent pas toujours pareil."""
        revue = service({"Élasticsearch": []}).lire(
            [avis("Multiples vulnérabilités dans elasticsearch (28 août 2026)")]
        )

        # Le nom rendu est le nom canonique déclaré, pas celui qu'a écrit l'avis.
        self.assertEqual(["Élasticsearch"], list(revue.avis[0].composants))

    def test_a_short_name_is_not_matched_inside_a_longer_word(self):
        """Le piège de l'appariement naïf : « Go » reconnu dans « Google Chrome ».

        C'est ce cas, et lui seul, qui interdit un simple `in` sur la chaîne. Un
        composant qui ressort tous les jours parce que son nom est court finit par
        rendre la phrase entière inutile.
        """
        revue = service({"Go": [], "R": []}).lire(
            [
                avis("Multiples vulnérabilités dans Google Chrome (26 août 2026)"),
                avis(
                    "Vulnérabilité dans Redmine (26 août 2026)",
                    "Elle permet de provoquer une atteinte à la confidentialité des données.",
                    item_id="avis-2",
                ),
            ]
        )

        self.assertEqual([], revue.avis)

    def test_a_multi_word_alias_needs_its_words_side_by_side(self):
        """« Apache Tomcat » ne doit pas se reconnaître dans un avis qui cite les deux séparément."""
        rendu = service({"Apache Tomcat": []})

        ensemble = rendu.lire([avis("Multiples vulnérabilités dans Apache Tomcat (26 août 2026)")])
        separes = rendu.lire(
            [
                avis(
                    "Multiples vulnérabilités dans Apache HTTP Server (26 août 2026)",
                    "Le connecteur vers Tomcat n'est pas concerné.",
                )
            ]
        )

        self.assertEqual(1, len(ensemble.avis))
        self.assertEqual([], separes.avis)

    def test_an_alias_matches_where_the_canonical_name_does_not(self):
        revue = service({"Keycloak": ["Red Hat Single Sign-On"]}).lire(
            [avis("Multiples vulnérabilités dans Red Hat Single Sign-On (25 août 2026)")]
        )

        self.assertEqual(["Keycloak"], list(revue.avis[0].composants))

    def test_an_advisory_touching_nothing_is_left_out(self):
        revue = service({"Keycloak": []}).lire(
            [avis("Multiples vulnérabilités dans Tenable Enclave Security (28 août 2026)")]
        )

        self.assertEqual([], revue.avis)
        self.assertEqual(1, revue.lus)

    def test_an_advisory_touching_two_components_names_both(self):
        """Le jour où un avis touche deux composants est précisément celui où on le veut."""
        revue = service({"noyau Linux": [], "Debian": []}).lire(
            [avis("Multiples vulnérabilités dans le noyau Linux de Debian (28 août 2026)")]
        )

        self.assertEqual(["noyau Linux", "Debian"], list(revue.avis[0].composants))
        self.assertIn("noyau Linux et Debian", revue.phrase)


class CriticiteTests(unittest.TestCase):
    """La criticité vient du vocabulaire de l'avis, jamais d'un jugement.

    Un avis CERT-FR ne porte ni score CVSS ni cotation : il nomme ce que la faille
    permet, dans une liste de tournures fixes. C'est là, et nulle part ailleurs, qu'il
    y a quelque chose à lire.
    """

    def test_the_impact_announced_by_the_advisory_is_read(self):
        criticite = certfr.criticite_de(
            "Elles permettent à un attaquant de provoquer une élévation de privilèges."
        )

        self.assertEqual("élévation de privilèges", criticite.libelle)

    def test_the_remote_variant_wins_over_the_plain_one(self):
        """« à distance » est contenu dans l'autre : l'ordre de l'échelle décide seul."""
        criticite = certfr.criticite_de(
            "Certaines d'entre elles permettent une exécution de code arbitraire à distance."
        )

        self.assertEqual("exécution de code arbitraire à distance", criticite.libelle)

    def test_the_gravest_impact_of_a_list_is_the_one_kept(self):
        criticite = certfr.criticite_de(
            "Elles permettent de provoquer une atteinte à la confidentialité des données, "
            "un déni de service et une élévation de privilèges."
        )

        self.assertEqual("élévation de privilèges", criticite.libelle)

    def test_an_advisory_without_a_known_impact_falls_back_explicitly(self):
        """Un champ vide se lirait comme une faille bénigne : le repli se dit."""
        criticite = certfr.criticite_de(
            "Multiples vulnérabilités à l'impact non spécifié par l'éditeur."
        )

        self.assertIs(certfr.INDETERMINEE, criticite)
        self.assertIn("non précisé", criticite.libelle)

    def test_the_scale_reads_accents_and_case_like_the_matching_does(self):
        self.assertEqual(
            "déni de service à distance",
            certfr.criticite_de("UN DENI DE SERVICE A DISTANCE").libelle,
        )


class PhraseTests(unittest.TestCase):
    """Une phrase, une seule, et qui se juge à sept heures du matin."""

    def test_a_single_match_is_named_with_its_impact(self):
        revue = service({"Keycloak": []}).lire(
            [
                avis(
                    "Multiples vulnérabilités dans Keycloak (25 août 2026)",
                    "Elles permettent une exécution de code arbitraire à distance.",
                ),
                avis("Vulnérabilité dans CPython (27 août 2026)", item_id="avis-2"),
            ]
        )

        self.assertEqual(
            "2 avis CERT-FR aujourd'hui, 1 touche la stack : "
            "Keycloak — exécution de code arbitraire à distance.",
            revue.phrase,
        )

    def test_several_matches_are_enumerated_gravest_first(self):
        revue = service({"noyau Linux": [], "Keycloak": []}).lire(
            [
                avis(
                    "Multiples vulnérabilités dans le noyau Linux de SUSE (28 août 2026)",
                    "Elles permettent de provoquer un déni de service.",
                ),
                avis(
                    "Multiples vulnérabilités dans Keycloak (25 août 2026)",
                    "Elles permettent une exécution de code arbitraire à distance.",
                    item_id="avis-2",
                ),
            ]
        )

        self.assertEqual(
            "2 avis CERT-FR aujourd'hui, 2 touchent la stack : "
            "Keycloak — exécution de code arbitraire à distance ; "
            "noyau Linux — déni de service.",
            revue.phrase,
        )
        # Les liens « À lire » de l'email suivent le même ordre que la phrase.
        self.assertEqual(
            ["avis-2", "avis-1"], [article.item_id for article in revue.touches]
        )

    def test_no_match_says_how_many_advisories_were_read(self):
        """« rien à signaler » sans dire sur combien ne se juge pas."""
        revue = service({"Keycloak": [], "Traefik": []}).lire(
            [avis("Multiples vulnérabilités dans Google Chrome (26 août 2026)")]
        )

        self.assertEqual(
            "1 avis CERT-FR aujourd'hui, aucun ne touche les 2 composants surveillés.",
            revue.phrase,
        )

    def test_a_single_watched_component_is_still_said_in_French(self):
        """« les 1 composant surveillé » ne se lit pas, et la phrase part en synthèse vocale."""
        revue = service({"Keycloak": []}).lire(
            [avis("Multiples vulnérabilités dans Google Chrome (26 août 2026)")]
        )

        self.assertEqual(
            "1 avis CERT-FR aujourd'hui, aucun ne touche le seul composant surveillé.",
            revue.phrase,
        )

    def test_an_empty_stack_says_so_rather_than_announcing_good_news(self):
        """Sans composant déclaré, « rien ne vous touche » serait faux tous les jours."""
        revue = service({}).lire(
            [avis("Multiples vulnérabilités dans Keycloak (25 août 2026)")]
        )

        self.assertEqual([], revue.avis)
        self.assertIn("aucun composant n'est déclaré", revue.phrase)


class StackDeclareeTests(unittest.TestCase):
    """La forme d'une entrée déclarée. Sa lecture depuis le document est dans `test_profil`."""

    def test_nothing_declared_leaves_an_empty_stack(self):
        """L'état du jour de l'installation : rien n'est apparié, et la phrase le dit."""
        self.assertTrue(certfr.Stack.declaree(None).vide)
        self.assertTrue(certfr.Stack.declaree([]).vide)

    def test_a_string_declares_a_component_without_alias(self):
        declaree = certfr.Stack.declaree(["Traefik"])

        self.assertEqual(1, len(declaree))
        self.assertEqual(
            ("Traefik",), declaree.concernes("Multiples vulnérabilités dans Traefik")
        )

    def test_an_object_declares_the_other_spellings(self):
        declaree = certfr.Stack.declaree([{"nom": "Keycloak", "alias": ["RH-SSO"]}])

        self.assertEqual(("Keycloak",), declaree.concernes("Vulnérabilité dans RH-SSO"))

    def test_both_forms_declare_the_same_stack(self):
        """L'empreinte porte sur ce qui est déclaré, pas sur la façon de l'écrire."""
        self.assertEqual(
            certfr.Stack.declaree(["Traefik"]).empreinte,
            certfr.Stack.declaree([{"nom": "Traefik"}]).empreinte,
        )

    def test_something_that_is_not_a_list_fails_at_startup(self):
        """La forme d'avant — un objet nom par nom — ne passe pas pour une liste vide."""
        with self.assertRaises(certfr.StackError):
            certfr.Stack.declaree({"Keycloak": {"alias": ["RH-SSO"]}})

    def test_an_entry_without_a_name_fails_at_startup(self):
        """Un composant sauté ne se remarque pas : il manque juste le seul avis attendu."""
        with self.assertRaises(certfr.StackError):
            certfr.Stack.declaree([{"alias": ["RH-SSO"]}])

    def test_a_malformed_alias_list_fails_at_startup(self):
        with self.assertRaises(certfr.StackError) as leve:
            certfr.Stack.declaree([{"nom": "Keycloak", "alias": "RH-SSO"}])

        self.assertIn("Keycloak", str(leve.exception))

    def test_a_component_that_nothing_could_match_fails_at_startup(self):
        with self.assertRaises(certfr.StackError):
            certfr.Stack.declaree(["---"])

    def test_the_fingerprint_changes_with_the_declared_list(self):
        """Deux journaux dont elle diffère n'ont pas été appariés contre la même stack."""
        une = stack({"Keycloak": []})
        autre = stack({"Keycloak": ["RH-SSO"]})

        self.assertEqual(une.empreinte, stack({"Keycloak": []}).empreinte)
        self.assertNotEqual(une.empreinte, autre.empreinte)


if __name__ == "__main__":
    unittest.main()
