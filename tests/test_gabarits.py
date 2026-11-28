"""Les gabarits métier sont des données fiables, pas du code métier déguisé."""

import tempfile
import unittest

from rssresume.categories import Catalogue
from rssresume.gabarits import CHEMIN_BUILTIN, Gabarits
from rssresume.profil import profil_depuis_dict


class GabaritsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def catalogue(self):
        return Catalogue.depuis_document(
            {
                "6 - Tech generaliste": {"description": "Tech.", "metiers": [], "visibilite": "publique"},
                "2 - Cybersecurite technique et menaces": {"description": "Cyber.", "metiers": [], "visibilite": "publique"},
                "3 - Conformite, reglementation et gouvernance": {"description": "Règles.", "metiers": [], "visibilite": "publique"},
                "1 - Alertes et avis CERT-FR ANSSI": {"description": "CERT.", "metiers": [], "visibilite": "publique"},
                "11 - Qualite logicielle et tests": {"description": "QA.", "metiers": [], "visibilite": "publique"},
                "12 - Gestion de produit": {"description": "Produit.", "metiers": [], "visibilite": "publique"},
                "13 - Design et UX": {"description": "UX.", "metiers": [], "visibilite": "publique"},
                "14 - Gestion de projet et agilite": {"description": "Projet.", "metiers": [], "visibilite": "publique"},
                "15 - Pilotage DSI": {"description": "DSI.", "metiers": [], "visibilite": "publique"},
            },
            "test",
        )

    def test_all_built_in_templates_pass_profile_and_catalogue_validation(self):
        gabarits = Gabarits.depuis_fichier(CHEMIN_BUILTIN, self.catalogue())

        metiers = {gabarit.metier for gabarit in gabarits}
        self.assertEqual(
            {"cto", "developpeur", "ops", "dsi", "rssi", "chef-de-projet", "qa", "po-pm", "designer"},
            metiers,
        )
        for gabarit in gabarits:
            profil_depuis_dict(gabarit.document, gabarit.metier, self.catalogue(), "")

    def test_templates_use_only_public_catalogue_categories(self):
        gabarits = Gabarits.depuis_fichier(CHEMIN_BUILTIN, self.catalogue())

        for gabarit in gabarits:
            for categorie in gabarit.document["categories"]:
                entree = self.catalogue().entree(categorie)
                self.assertIsNotNone(entree)
                self.assertTrue(entree.publique)

    def test_templates_do_not_name_a_company(self):
        gabarits = Gabarits.depuis_fichier(CHEMIN_BUILTIN)

        texte = "\n".join(
            gabarit.libelle + " " + gabarit.document["profil"]
            for gabarit in gabarits
        ).lower()
        for entreprise in ("transfertpro", "microsoft", "google", "amazon", "apple", "meta"):
            self.assertNotIn(entreprise, texte)

    def test_chaque_gabarit_porte_les_trois_rubriques_de_la_trame(self):
        """La page profil illustre sa trame par un gabarit : le texte doit la suivre.

        Les trois libellés sont ceux de l'aide de la page profil : « Mon métier »,
        « Ce que je veux suivre », « Ce qui ne m'intéresse pas ».
        """
        gabarits = Gabarits.depuis_fichier(CHEMIN_BUILTIN)

        rubriques = ("mon métier", "ce que je veux suivre", "ce qui ne m'intéresse pas")
        for gabarit in gabarits:
            texte = gabarit.document["profil"].lower()
            for rubrique in rubriques:
                with self.subTest(metier=gabarit.metier, rubrique=rubrique):
                    self.assertIn(rubrique, texte)
