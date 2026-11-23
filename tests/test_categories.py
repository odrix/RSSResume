"""Le catalogue des catégories : ce qu'il accepte, et à qui il sert quoi.

Ce que ces tests protègent :

- la validation, tout ou rien, avec le libellé fautif dans le message : une catégorie
  privée mal écrite ne doit ni passer ni disparaître en silence ;
- la règle fermée : décrite et visible, servie ; absente, servie à personne ;
- l'exemple du dépôt, qui doit rester un catalogue valide.
"""

import json
import pathlib
import tempfile
import unittest

from rssresume.categories import Catalogue, CatalogueOuvert, CategorieCatalogue

EXEMPLE = pathlib.Path(__file__).resolve().parent.parent / "docs" / "categories.exemple.json"


def publique(**autres):
    return {"description": "Une catégorie.", "metiers": ["cto"], "visibilite": "publique", **autres}


def privee(**autres):
    return {
        "description": "Une veille.",
        "metiers": ["cto"],
        "visibilite": "privee",
        "proprietaires": ["adrien"],
        **autres,
    }


class CatalogueLectureTests(unittest.TestCase):
    def test_a_valid_document_is_read_and_comments_are_skipped(self):
        catalogue = Catalogue.depuis_document(
            {"_note": ["commentaire"], "Tech": publique(), "Veille marché": privee()}, "test"
        )

        self.assertFalse(catalogue.ouvert)
        self.assertEqual(["Tech", "Veille marché"], [e.libelle for e in catalogue.entrees()])
        self.assertTrue(catalogue.entree("tech").publique)
        self.assertEqual(("adrien",), catalogue.entree("Veille marche").proprietaires)

    def test_every_faulty_entry_raises_with_its_label(self):
        fautes = {
            "clé inconnue": publique(couleur="rouge"),
            "visibilité absente": {"description": "x", "metiers": []},
            "visibilité hors liste": publique(visibilite="interne"),
            "privée sans propriétaire": privee(proprietaires=[]),
            "privée sans liste": privee(proprietaires="adrien"),
            "publique avec propriétaires": publique(proprietaires=["adrien"]),
            "propriétaire invalide": privee(proprietaires=["Adrien Martin"]),
            "description vide": publique(description="  "),
            "description absente": {"metiers": [], "visibilite": "publique"},
            "métiers pas une liste": publique(metiers="cto"),
            "métier vide": publique(metiers=["cto", ""]),
            "métier pas un texte": publique(metiers=[3]),
            "entrée pas un objet": "publique",
        }
        for cas, entree in fautes.items():
            with self.subTest(cas):
                with self.assertRaises(ValueError) as leve:
                    Catalogue.depuis_document({"Tech": publique(), "Fautive": entree}, "test")
                self.assertIn("Fautive", str(leve.exception))

    def test_two_labels_equal_once_folded_are_refused(self):
        with self.assertRaises(ValueError) as leve:
            Catalogue.depuis_document({"Veille marché": publique(), "veille MARCHE": publique()}, "test")
        self.assertIn("Veille marché", str(leve.exception))
        self.assertIn("veille MARCHE", str(leve.exception))

    def test_a_document_that_is_not_an_object_or_is_empty_is_refused(self):
        for document in ([], "texte", {}, {"_note": "rien d'autre"}):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    Catalogue.depuis_document(document, "test")

    def test_an_invalid_json_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "categories.json"
            fichier.write_text('{"Tech": ', encoding="utf-8")
            with self.assertRaises(ValueError) as leve:
                Catalogue.depuis_fichier(fichier)
        self.assertIn("JSON", str(leve.exception))

    def test_an_underscore_key_holding_an_object_is_a_category_not_a_comment(self):
        """Une vraie catégorie FreshRSS peut s'appeler `_Archive` : seule la valeur tranche."""
        catalogue = Catalogue.depuis_document(
            {"_note": "commentaire", "_liste": ["aussi"], "_Archive": publique()}, "test"
        )

        self.assertEqual(["_Archive"], [e.libelle for e in catalogue.entrees()])
        with self.assertRaises(ValueError) as leve:
            Catalogue.depuis_document({"Tech": publique(), "_Fautive": {"metiers": []}}, "test")
        self.assertIn("_Fautive", str(leve.exception))

    def test_labels_compare_trimmed_on_both_sides(self):
        catalogue = Catalogue.depuis_document({" Veille marché ": privee()}, "test")

        self.assertEqual("Veille marché", catalogue.entrees()[0].libelle)
        self.assertEqual(["veille MARCHE  "], catalogue.servies(["veille MARCHE  "], "adrien"))
        self.assertEqual([], catalogue.hors_catalogue(["  Veille marché"]))
        with self.assertRaises(ValueError):
            Catalogue.depuis_document({"Tech": publique(), " tech ": publique()}, "test")

    def test_an_owner_unknown_to_the_directory_is_not_an_error(self):
        """La personne peut s'inscrire après que sa catégorie a été décrite."""
        catalogue = Catalogue.depuis_document({"Veille": privee(proprietaires=["pas-encore-la"])}, "test")
        self.assertEqual(("pas-encore-la",), catalogue.entree("Veille").proprietaires)

    def test_the_documented_example_is_a_valid_catalogue(self):
        catalogue = Catalogue.depuis_fichier(EXEMPLE)

        self.assertIsNotNone(catalogue.entree("Veille concurrentielle"))
        self.assertFalse(catalogue.entree("Veille concurrentielle").publique)
        self.assertTrue(any(entree.publique for entree in catalogue.entrees()))

    def test_the_exchange_form_reads_back_identically(self):
        document = {"Tech": publique(), "Veille": privee()}
        relu = Catalogue.depuis_document(
            json.loads(json.dumps(Catalogue.depuis_document(document, "test").en_document())), "relu"
        )
        self.assertEqual(document, relu.en_document())


class CatalogueServiesTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = Catalogue(
            [
                CategorieCatalogue("Tech", "Tech.", ["developpeur"]),
                CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["adrien"]),
            ]
        )

    def test_a_private_category_is_served_only_to_its_owners(self):
        categories = ["Veille marché", "Tech"]

        self.assertEqual(["Veille marché", "Tech"], self.catalogue.servies(categories, "adrien"))
        self.assertEqual(["Tech"], self.catalogue.servies(categories, "bea"))
        self.assertTrue(self.catalogue.servie_a("Veille marché", ["bea", "adrien"]))
        self.assertFalse(self.catalogue.servie_a("Veille marché", ["bea"]))

    def test_a_category_missing_from_the_catalogue_is_served_to_nobody(self):
        categories = ["Tech", "Nouvelle", "VEILLE MARCHE"]

        self.assertEqual(["Tech", "VEILLE MARCHE"], self.catalogue.servies(categories, "adrien"))
        self.assertEqual(["Nouvelle"], self.catalogue.hors_catalogue(categories))
        self.assertFalse(self.catalogue.servie_a("Nouvelle", ["adrien", "bea"]))

    def test_proposables_are_public_ones_and_own_private_ones(self):
        catalogue = Catalogue(
            [
                CategorieCatalogue("Tech", "Tech.", ["developpeur"]),
                CategorieCatalogue("Veille marché", "Veille.", ["cto"], ["adrien"]),
                CategorieCatalogue("Veille interne", "Interne.", ["cto"], ["bea"]),
            ]
        )

        self.assertEqual(["Tech", "Veille marché"], [e.libelle for e in catalogue.proposables("adrien")])
        self.assertEqual(["Tech", "Veille interne"], [e.libelle for e in catalogue.proposables("bea")])
        self.assertEqual(
            {"libelle": "Veille marché", "description": "Veille.", "privee": True},
            catalogue.entree("Veille marché").proposition_json(),
        )
        # Le refus cite la même liste que la page propose, jamais la privée d'un autre.
        with self.assertRaises(ValueError) as leve:
            catalogue.abonnement(["Veille interne"], "adrien", "adrien")
        self.assertTrue(str(leve.exception).endswith("Catégories proposées : Tech, Veille marché."))
        self.assertEqual([], CatalogueOuvert().proposables("adrien"))

    def test_an_open_catalogue_serves_everything_to_everyone(self):
        ouvert = CatalogueOuvert()

        self.assertTrue(ouvert.ouvert)
        self.assertEqual(["Veille", "Nouvelle"], ouvert.servies(["Veille", "Nouvelle"], "bea"))
        self.assertEqual([], ouvert.hors_catalogue(["Nouvelle"]))
        self.assertTrue(ouvert.servie_a("Nouvelle", ["bea"]))


if __name__ == "__main__":
    unittest.main()
