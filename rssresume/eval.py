"""Évaluation locale du prompt de scoring sur un jeu de référence versionné.

Le jeu porte les données de cas attendues, sans appeler un fournisseur au chargement.
Le mode réel ouvre les mêmes journaux que le pipeline afin que le coût soit lu de
`runlog` puis tarifié par `pricing`, exactement comme pour un digest ordinaire.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pathlib
import tempfile

from rssresume import llm, runlog
from rssresume.llm import providers

#: Emplacement par défaut du jeu livré avec le dépôt.
JEU_DE_REFERENCE = pathlib.Path(__file__).parent.parent / "tests" / "eval" / "reference.json"

VERDICT_DOIT = "doit"
VERDICT_NE_DOIT_PAS = "ne doit pas"
VERDICT_VALIDES = (VERDICT_DOIT, VERDICT_NE_DOIT_PAS)


class EvalError(ValueError):
    """Format de jeu ou résultat impossible à interpréter sans ambiguïté."""


@dataclasses.dataclass(frozen=True)
class ArticleEval:
    """Un cas du jeu : son contenu public et les bornes humaines attendues."""

    id: str
    titre: str
    resume: str
    note_min: int
    note_max: int
    verdict: str


@dataclasses.dataclass(frozen=True)
class JeuEval:
    """Le jeu chargé, avec son seuil de lecture utilisé pour le verdict."""

    articles: list[ArticleEval]
    seuil: int


@dataclasses.dataclass(frozen=True)
class CasEval:
    """Le résultat d'un article : score rendu, attentes et écarts."""

    article: ArticleEval
    score: int
    hors_fourchette: bool
    faux_positif: bool
    faux_negatif: bool


@dataclasses.dataclass(frozen=True)
class BilanEval:
    """Les quatre compteurs qui permettent de comparer deux prompts."""

    cas: list[CasEval]

    @property
    def hors_fourchette(self) -> int:
        return sum(cas.hors_fourchette for cas in self.cas)

    @property
    def faux_positifs(self) -> int:
        return sum(cas.faux_positif for cas in self.cas)

    @property
    def faux_negatifs(self) -> int:
        return sum(cas.faux_negatif for cas in self.cas)

    def texte(self) -> str:
        return (
            "Évaluation du scoring\n"
            f"  articles : {len(self.cas)}\n"
            f"  notes hors fourchette : {self.hors_fourchette}\n"
            f"  faux positifs : {self.faux_positifs}\n"
            f"  faux négatifs : {self.faux_negatifs}"
        )


def charger_jeu(path: pathlib.Path | str = JEU_DE_REFERENCE) -> JeuEval:
    """Charge et valide un jeu sans cacher une donnée de cas mal formée."""
    chemin = pathlib.Path(path)
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"Jeu d'évaluation illisible ({chemin}) : {exc}") from exc
    if not isinstance(brut, dict):
        raise EvalError("Le jeu d'évaluation doit être un objet JSON.")

    seuil = brut.get("seuil", 7)
    if isinstance(seuil, bool) or not isinstance(seuil, int) or not 0 <= seuil <= 10:
        raise EvalError("« seuil » doit être un entier de 0 à 10.")

    articles = brut.get("articles")
    if not isinstance(articles, list) or not 30 <= len(articles) <= 50:
        raise EvalError("« articles » doit contenir entre 30 et 50 cas.")

    charges: list[ArticleEval] = []
    identifiants: set[str] = set()
    for numero, entree in enumerate(articles, start=1):
        if not isinstance(entree, dict):
            raise EvalError(f"Article {numero} : objet JSON attendu.")
        identifiant = entree.get("id")
        titre = entree.get("titre")
        resume = entree.get("resume")
        fourchette = entree.get("note_attendue")
        verdict = entree.get("verdict")
        if not isinstance(identifiant, str) or not identifiant.strip():
            raise EvalError(f"Article {numero} : « id » non vide attendu.")
        if identifiant in identifiants:
            raise EvalError(f"Article {numero} : identifiant dupliqué « {identifiant} ».")
        identifiants.add(identifiant)
        if not isinstance(titre, str) or not titre.strip():
            raise EvalError(f"Article {identifiant} : « titre » non vide attendu.")
        if not isinstance(resume, str) or not resume.strip():
            raise EvalError(f"Article {identifiant} : « resume » non vide attendu.")
        if not isinstance(fourchette, list) or len(fourchette) != 2:
            raise EvalError(f"Article {identifiant} : « note_attendue » doit être [min, max].")
        note_min, note_max = fourchette
        if (
            isinstance(note_min, bool)
            or isinstance(note_max, bool)
            or not isinstance(note_min, int)
            or not isinstance(note_max, int)
            or not 0 <= note_min <= note_max <= 10
        ):
            raise EvalError(f"Article {identifiant} : fourchette invalide {fourchette}.")
        if verdict not in VERDICT_VALIDES:
            raise EvalError(
                f"Article {identifiant} : verdict attendu « doit » ou « ne doit pas »."
            )
        charges.append(
            ArticleEval(
                id=identifiant,
                titre=titre,
                resume=resume,
                note_min=note_min,
                note_max=note_max,
                verdict=verdict,
            )
        )
    return JeuEval(articles=charges, seuil=seuil)


def evaluer(jeu: JeuEval, scorer, seuil: int | None = None, profil: str | None = None) -> BilanEval:
    """Note les cas avec un vrai fournisseur ou une doublure et compare le résultat."""
    seuil_applique = jeu.seuil if seuil is None else seuil
    if isinstance(seuil_applique, bool) or not isinstance(seuil_applique, int) or not 0 <= seuil_applique <= 10:
        raise EvalError("Le seuil doit être un entier de 0 à 10.")

    articles = [
        {"id": article.id, "title": article.titre, "summary": article.resume}
        for article in jeu.articles
    ]
    notes = scorer.score_articles(articles, profil=profil)
    if not isinstance(notes, list) or len(notes) != len(articles):
        raise EvalError(
            f"Le noteur a rendu {len(notes) if isinstance(notes, list) else 'une réponse'} "
            f"au lieu de {len(articles)} notes."
        )

    notes_par_id = {str(note.get("id")): note for note in notes if isinstance(note, dict)}
    cas: list[CasEval] = []
    for article in jeu.articles:
        note = notes_par_id.get(article.id)
        if note is None:
            raise EvalError(f"Le noteur n'a pas rendu de note pour « {article.id} ».")
        score = note.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 10:
            raise EvalError(f"Le noteur a rendu une note invalide pour « {article.id} » : {score}.")
        hors_fourchette = not article.note_min <= score <= article.note_max
        verdict_predit = VERDICT_DOIT if score >= seuil_applique else VERDICT_NE_DOIT_PAS
        cas.append(
            CasEval(
                article=article,
                score=score,
                hors_fourchette=hors_fourchette,
                faux_positif=(verdict_predit == VERDICT_DOIT and article.verdict == VERDICT_NE_DOIT_PAS),
                faux_negatif=(verdict_predit == VERDICT_NE_DOIT_PAS and article.verdict == VERDICT_DOIT),
            )
        )
    return BilanEval(cas=cas)


def main(argv: list[str] | None = None) -> int:
    """Commande réelle : charge le jeu, appelle le scoring, affiche bilan et coût."""
    parser = argparse.ArgumentParser(description="Évaluer le prompt de scoring sur le jeu de référence.")
    parser.add_argument("--jeu", type=pathlib.Path, default=JEU_DE_REFERENCE, help="Fichier JSON du jeu de référence")
    parser.add_argument("--seuil", type=int, help="Seuil de verdict, par défaut celui du jeu")
    parser.add_argument("--profil", help="Profil de pertinence injecté au modèle")
    args = parser.parse_args(argv)

    try:
        jeu = charger_jeu(args.jeu)
        scorer = llm.for_action(providers.SCORING)
        if scorer is None:
            from rssresume.tools import console
            console.error("Évaluation : aucun fournisseur de scoring configuré (clé API absente).")
            return 1

        with tempfile.TemporaryDirectory() as dossier:
            jour = dt.date.today()
            chemin = pathlib.Path(dossier)
            with runlog.day_scope(jour, chemin) as journal:
                with runlog.category_scope("Évaluation", "evaluation", jour, chemin):
                    bilan = evaluer(jeu, scorer, args.seuil, args.profil)

        from rssresume.tools import console
        console.log(bilan.texte())
        console.log(journal.cumul().texte())
        return 0
    except EvalError as exc:
        from rssresume.tools import console
        console.error(f"Évaluation : {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
