import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume import eval as evaluation


class DoublureScorer:
    def __init__(self, scores):
        self.scores = scores

    def score_articles(self, articles, profil=None):
        return [
            {"id": article["id"], "score": self.scores[article["id"]], "thematique": "autre", "angle": ""}
            for article in articles
        ]


class JeuTests(unittest.TestCase):
    def test_score_exact_sur_trois_articles(self):
        jeu = evaluation.JeuEval(
            articles=[
                evaluation.ArticleEval("a", "API publique", "Nouvelle API", 8, 10, "doit"),
                evaluation.ArticleEval("b", "Casque", "Produit grand public", 0, 3, "ne doit pas"),
                evaluation.ArticleEval("c", "Facturation cloud", "Hausse des tarifs", 5, 7, "doit"),
            ],
            seuil=7,
        )
        doublure = DoublureScorer({"a": 9, "b": 8, "c": 4})

        bilan = evaluation.evaluer(jeu, doublure)

        self.assertEqual(2, bilan.hors_fourchette)
        self.assertEqual(1, bilan.faux_positifs)
        self.assertEqual(1, bilan.faux_negatifs)

    def test_format_charge_et_valide(self):
        jeu = evaluation.charger_jeu()

        self.assertGreaterEqual(len(jeu.articles), 30)
        self.assertLessEqual(len(jeu.articles), 50)

    def test_format_refuse_un_article_hors_fourchette(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = pathlib.Path(dossier) / "jeu.json"
            chemin.write_text(json.dumps({
                "seuil": 7,
                "articles": [
                    {"id": str(numero), "titre": "Titre", "resume": "Résumé",
                     "note_attendue": [11, 12], "verdict": "doit"}
                    for numero in range(30)
                ],
            }), encoding="utf-8")

            with self.assertRaises(evaluation.EvalError):
                evaluation.charger_jeu(chemin)

    def test_aucune_donnee_personnelle_n_est_declaree(self):
        jeu = evaluation.charger_jeu()
        secrets = ("adrien", "nom personnel", "adresse", "email", "téléphone", "mot de passe")
        for article in jeu.articles:
            texte = f"{article.titre} {article.resume}".casefold()
            for secret in secrets:
                self.assertNotIn(secret, texte)

    def test_commande_affiche_le_bilan_et_le_cout(self):
        doublure = DoublureScorer({article.id: 7 for article in evaluation.charger_jeu().articles})
        with mock.patch.object(evaluation.llm, "for_action", return_value=doublure):
            with mock.patch("rssresume.tools.console.log") as sortie:
                code = evaluation.main(["--jeu", str(evaluation.JEU_DE_REFERENCE)])

        self.assertEqual(0, code)
        affichage = "\n".join(str(call.args[0]) for call in sortie.call_args_list)
        self.assertIn("Évaluation du scoring", affichage)
        self.assertIn("Consommation IA", affichage)


if __name__ == "__main__":
    unittest.main()
