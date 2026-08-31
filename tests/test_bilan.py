"""Le bilan d'une journée déjà produite, relu de ses journaux.

Ce que ces tests protègent : c'est ce qu'on lit quand une journée s'est mal passée, sur
un serveur où l'on n'entre que par SSH. Trois choses doivent y être justes, parce qu'on
prend des décisions dessus — le seuil RÉELLEMENT appliqué, le coût quand il est inconnu,
et la présence des catégories qui n'ont pas de journal du tout.
"""

import datetime as dt
import json
import pathlib
import tempfile
import unittest

from rssresume import runlog

JOUR = dt.date(2026, 8, 30)


def journal(
    categorie="2 - Cyber",
    statut="audio",
    articles=1,
    retenus=1,
    seuil_applique=7,
    cout=0.001234,
    audio="2-cyber.mp3",
    marqueur=None,
    deterministe=False,
    entrees=(),
    appels=(),
):
    """Un `<categorie>.log.json` tel que `runlog` l'écrit, réduit à ce que le bilan lit."""
    parametres = {"langue": "fr"}
    if deterministe:
        parametres["traitement"] = runlog.TRAITEMENT_DETERMINISTE
    else:
        parametres["seuil"] = 7
    return {
        "categorie": categorie,
        "date": JOUR.isoformat(),
        "parametres": parametres,
        "resultat": {
            "statut": statut,
            "articles": articles,
            "retenus": retenus,
            "seuil_applique": seuil_applique,
            "audio": audio,
            "marqueur": marqueur,
        },
        "couts": {"devise": "USD", "total": cout, "appels": list(appels)},
        "articles": list(entrees),
    }


def appel(typologie="resume", modele="gpt-5.6-luna", entree=100, sortie=50, cout=None):
    return {
        "typologie": typologie,
        "type_appel": typologie,
        "modele": modele,
        "tokens_entree": entree,
        "tokens_sortie": sortie,
        "tokens_raisonnement": 0,
        "cout": cout,
    }


def ecrire(racine, journaux=(), journee=None, marqueurs=()):
    """Écrit une journée sur le disque et rend son bilan."""
    day_dir = pathlib.Path(racine) / JOUR.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    for index, contenu in enumerate(journaux, start=1):
        (day_dir / f"{index}-categorie{runlog.LOG_SUFFIX}").write_text(
            json.dumps(contenu, ensure_ascii=False), encoding="utf-8"
        )
    if journee is not None:
        (day_dir / runlog.DAY_LOG_NAME).write_text(
            json.dumps(journee, ensure_ascii=False), encoding="utf-8"
        )
    for nom in marqueurs:
        (day_dir / nom).write_text("", encoding="utf-8")
    return runlog.lire_bilan(day_dir, JOUR)


class EnteteTests(unittest.TestCase):
    def test_the_header_names_the_day_and_where_it_lives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal()]).texte()

            self.assertIn("Journée du 2026-08-30", texte)
            self.assertIn(JOUR.isoformat(), texte)

    def test_a_day_audio_is_named_with_its_origin(self):
        """« assemblage » dit que le modèle n'a pas répondu et que les résumés sont
        partis bout à bout : c'est la première chose à voir quand un audio a mal sonné."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journee = {"montage": {"audio": "journee.mp3", "origine": "assemblage"}}
            texte = ecrire(tmpdir, [journal()], journee=journee).texte()

            self.assertIn("audio : journee.mp3 (assemblage)", texte)

    def test_by_category_the_files_are_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(audio="a.mp3"), journal(audio="b.mp3")]).texte()

            self.assertIn("audio : 2 fichier(s) par catégorie", texte)

    def test_a_day_without_any_audio_says_nothing_about_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(audio=None)]).texte()

            self.assertNotIn("audio :", texte)


class TableauTests(unittest.TestCase):
    def test_the_threshold_shown_is_the_one_that_actually_sorted(self):
        """Le seuil de la configuration valait 7 ; le repli l'a fait tomber à 5. C'est 5
        qui a trié la journée, et c'est le seul chiffre qui explique ce qu'on lit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(seuil_applique=5)]).texte()

            ligne, = [l for l in texte.splitlines() if l.startswith("2 - Cyber")]
            self.assertIn(" 5 ", ligne)
            self.assertNotIn(" 7 ", ligne)

    def test_the_status_and_the_counts_are_shown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(
                tmpdir, [journal(statut="aucun-article-retenu", articles=24, retenus=0)]
            ).texte()

            ligne, = [l for l in texte.splitlines() if l.startswith("2 - Cyber")]
            self.assertIn("aucun-article-retenu", ligne)
            self.assertIn("24", ligne)

    def test_an_unpriced_model_shows_a_question_mark_not_a_zero(self):
        """Un « 0.000000 » se lirait « rien dépensé » là où la réponse est « on ne sait pas »."""
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(cout=None)]).texte()

            ligne, = [l for l in texte.splitlines() if l.startswith("2 - Cyber")]
            self.assertTrue(ligne.rstrip().endswith("?"), ligne)
            self.assertNotIn("0.000000", ligne)

    def test_a_deterministic_category_has_no_threshold_to_show(self):
        """L'écrire ferait croire à un tri qui n'a pas eu lieu : ici rien n'a été jugé."""
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(
                tmpdir, [journal(statut="deterministe", deterministe=True, seuil_applique=None)]
            ).texte()

            ligne, = [l for l in texte.splitlines() if l.startswith("2 - Cyber")]
            self.assertIn("—", ligne)

    def test_a_very_long_category_name_does_not_break_the_columns(self):
        """Un libellé qui déborde la fenêtre du terminal fait perdre le tableau entier :
        il est tronqué, et les colonnes des deux lignes restent en face l'une de l'autre."""
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(
                tmpdir, [journal(categorie="C" * 90), journal(categorie="Courte")]
            ).texte()

            longue, = [l for l in texte.splitlines() if l.startswith("CCC")]
            courte, = [l for l in texte.splitlines() if l.startswith("Courte")]
            # Coupé à la largeur maximale, donc suivi d'une espace et non d'un « C ».
            self.assertTrue(longue.startswith("C" * runlog.LARGEUR_CATEGORIE_MAX + " "), longue)
            self.assertEqual(len(courte), len(longue))


class MarqueursTests(unittest.TestCase):
    def test_a_category_without_any_journal_still_appears(self):
        """Elle n'a rien lu ni rien dépensé, donc pas de journal — mais elle fait partie
        de la journée, et son absence du bilan se lirait comme un oubli."""
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal()], marqueurs=["9-vide.no-article"]).texte()

            self.assertIn("Sans journal", texte)
            self.assertIn("9-vide.no-article", texte)

    def test_a_marker_already_named_by_its_journal_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(
                tmpdir,
                [journal(statut="aucun-article-retenu", marqueur="7-ia.no-article")],
                marqueurs=["7-ia.no-article"],
            ).texte()

            self.assertNotIn("Sans journal", texte)


class DetailTests(unittest.TestCase):
    ARTICLES = (
        {
            "titre": "Une faille dans Traefik",
            "score": 9,
            "thematique": "cyber",
            "origine_note": "tags",
            "retenu": True,
        },
        {
            "titre": "Un article sans note",
            "score": None,
            "thematique": None,
            "origine_note": "aucune",
            "retenu": False,
        },
    )

    def test_the_articles_are_hidden_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(entrees=self.ARTICLES)]).texte()

            self.assertNotIn("Une faille dans Traefik", texte)

    def test_the_detail_shows_the_score_the_origin_and_the_selection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(entrees=self.ARTICLES)]).texte(detail=True)

            ligne, = [l for l in texte.splitlines() if "Traefik" in l]
            self.assertIn("9/10", ligne)
            self.assertIn("cyber", ligne)
            self.assertIn("retenu", ligne)
            # L'origine explique une journée qui n'a rien coûté : tout relu des tags.
            self.assertIn("tags", ligne)

    def test_an_article_the_model_left_unscored_shows_no_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal(entrees=self.ARTICLES)]).texte(detail=True)

            ligne, = [l for l in texte.splitlines() if "sans note" in l]
            self.assertIn("?/10", ligne)


class CoutsTests(unittest.TestCase):
    def test_the_day_and_the_categories_are_totalled_together(self):
        """Le montage et l'éphéméride ne se rattachent à aucune catégorie : sans le
        journal de la journée, le total tairait ce que le mode global coûte."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bilan = ecrire(
                tmpdir,
                [journal(appels=[appel("resume", "gpt-4o-mini", cout=0.001)])],
                journee={"couts": {"appels": [appel("montage", "gpt-4o-mini", cout=0.002)]}},
            )

            texte = bilan.texte()
            self.assertIn("résumé", texte)
            self.assertIn("montage", texte)
            self.assertIn("2 appel(s)", texte)

    def test_a_single_unpriced_call_makes_the_whole_total_unknown(self):
        """Le même arbitrage que le journal : pas de somme partielle, qui se lirait
        exactement comme une somme complète."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bilan = ecrire(
                tmpdir,
                [
                    journal(appels=[appel("resume", "gpt-4o-mini", cout=0.001)]),
                    journal(appels=[appel("resume", "modele-inconnu", cout=None)]),
                ],
            )

            self.assertIn("coût inconnu", bilan.texte())
            self.assertIn("modele-inconnu", bilan.texte())

    def test_a_day_replayed_from_the_cache_says_it_spent_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            texte = ecrire(tmpdir, [journal()]).texte()

            self.assertIn("aucun appel au fournisseur", texte)


class RobustesseTests(unittest.TestCase):
    def test_a_day_that_was_never_produced_is_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bilan = runlog.lire_bilan(pathlib.Path(tmpdir) / "2026-01-01", JOUR)

            self.assertTrue(bilan.vide)

    def test_an_unreadable_journal_is_skipped_rather_than_fatal(self):
        """Cette commande sert quand quelque chose ne va pas : elle ne doit pas être la
        deuxième chose à tomber."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bilan = ecrire(tmpdir, [journal()])
            (bilan.day_dir / f"9-casse{runlog.LOG_SUFFIX}").write_text("{ pas du json",
                                                                      encoding="utf-8")
            bilan = runlog.lire_bilan(bilan.day_dir, JOUR)

            self.assertEqual(1, len(bilan.categories))
            self.assertFalse(bilan.vide)
            self.assertIn("2 - Cyber", bilan.texte())


if __name__ == "__main__":
    unittest.main()
