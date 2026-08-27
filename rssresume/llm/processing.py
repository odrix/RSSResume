"""Relecture des réponses du noteur, et sélection des articles retenus.

Ce module ne parle à aucun fournisseur : il reçoit du texte et rend des dictionnaires.
Ce découpage lui vaut d'être le seul endroit à connaître les défauts d'une réponse de
modèle — JSON enveloppé de Markdown, lot incomplet, numéro recopié de travers — et
d'être testable sans réseau.

Lancé seul (`python -m rssresume.llm.processing`), il fait la démonstration complète du
scoring puis du résumé sur trois articles en dur, avec le fournisseur configuré.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from rssresume.llm import prompts
from rssresume.models import DEFAULT_THEMATIQUE, THEMATIQUES

logger = logging.getLogger(__name__)


class ProcessingError(RuntimeError):
    """Réponse du modèle inexploitable : JSON invalide, ou lot entièrement perdu.

    Un lot seulement incomplet n'en fait pas partie : les notes manquantes sont
    signalées article par article, pas levées (voir `read_scores`).

    Les échecs propres au fournisseur (HTTP, réponse tronquée) remontent en `llm.LLMError`.
    """


def scoring_fingerprint(profil: str | None, model: str) -> str:
    """Empreinte courte du prompt de notation, profil et modèle compris.

    Sert de clé de cache côté tags FreshRSS : toute retouche du profil, du barème ou du
    modèle produit une empreinte différente et déclenche donc la renotation. C'est ce qui
    rend le profil injectable sans risque — changer de profil ne peut pas laisser traîner
    des scores calculés contre l'ancien.
    """
    material = f"{prompts.scoring_system(profil)}\n{model}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def full_text(article: dict) -> str:
    """Texte intégral si disponible, résumé court sinon."""
    return (article.get("content") or "").strip() or (article.get("summary") or "").strip()


def read_scores(raw: str, lot: list[dict]) -> list[dict]:
    """Relit la réponse d'un lot de notation et la réaligne sur les articles envoyés.

    Renvoie {id, score, thematique, angle, notee} par article du lot, dans l'ordre
    d'envoi. `notee` est faux quand le modèle n'a rien rendu pour cet article : trente-neuf
    notes sur quarante faisaient échouer la catégorie en cours et toutes les suivantes,
    alors que le réalignement sait déjà où sont les trous. L'article manquant sort donc
    avec un score nul et le drapeau baissé — c'est à l'appelant de décider ce qu'il en
    fait, et `digest.py` choisit de ne pas le noter du tout plutôt que de figer un zéro.

    Une réponse dont RIEN n'est exploitable reste une erreur : ce n'est plus un trou dans
    un lot, c'est un lot qui n'a pas été traité.
    """
    alignees = _by_rank(_resultats(_extract_json(raw)), len(lot))
    manquantes = [article for article, note in zip(lot, alignees) if not note]
    if len(manquantes) == len(lot):
        raise ProcessingError(
            f"Aucune note exploitable dans la réponse : {len(lot)} article(s) envoyé(s)."
        )
    if manquantes:
        logger.warning(
            "Scoring : %d note(s) manquante(s) sur %d, article(s) laissé(s) sans note : %s",
            len(manquantes),
            len(lot),
            " | ".join(str(article.get("title") or article.get("id")) for article in manquantes),
        )
    return [
        {
            "id": str(article["id"]),
            "score": _clean_score(note.get("score")),
            "thematique": _clean_thematique(note.get("thematique")),
            "angle": str(note.get("angle") or "").strip(),
            # Faux pour un trou du lot : la note qui suit est une valeur de remplissage,
            # pas un jugement du modèle.
            "notee": bool(note),
        }
        for article, note in zip(lot, alignees)
    ]


def select(scored: list[dict], known_ids: set[str], seuil: int, max_items: int) -> list[dict]:
    """Les notes qui atteignent le seuil, les mieux notées d'abord, plafonnées."""
    retenus = sorted(
        (item for item in scored if item["score"] >= seuil and str(item["id"]) in known_ids),
        key=lambda item: item["score"],
        reverse=True,
    )
    logger.info("Sélection : %d article(s) au-dessus du seuil", len(retenus))
    return retenus[:max_items]


def _extract_json(text: str) -> Any:
    """Parse du JSON éventuellement enveloppé dans une clôture Markdown."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProcessingError(f"Réponse non-JSON du modèle : {cleaned[:300]!r}") from exc


def _resultats(parsed: Any) -> list[dict]:
    """Accepte {"resultats": [...]} comme une liste nue, par tolérance."""
    if isinstance(parsed, dict):
        parsed = parsed.get("resultats")
    if not isinstance(parsed, list):
        raise ProcessingError("Le JSON renvoyé ne contient pas de liste 'resultats'.")
    return parsed


def _clean_score(value: Any) -> int:
    """Ramène le score dans 0-10, 0 si le modèle a renvoyé n'importe quoi."""
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return 0


def _clean_thematique(value: Any) -> str:
    """Contraint la thématique à la liste fermée."""
    candidate = str(value or "").strip().lower()
    return candidate if candidate in THEMATIQUES else DEFAULT_THEMATIQUE


def _by_rank(resultats: list[dict], taille: int) -> list[dict]:
    """Réaligne les notes sur les articles envoyés, par numéro puis, à défaut, par position.

    Le modèle reçoit des numéros de 1 à N, pas les identifiants FreshRSS : une note dont le
    numéro est illisible ou dupliqué est rattachée à la première place encore libre, l'ordre
    de réponse étant imposé par le prompt. Les identifiants longs, eux, étaient recopiés de
    travers assez souvent pour faire échouer tout le lot.
    """
    par_rang: list[dict | None] = [None] * taille
    en_attente: list[dict] = []

    for item in resultats:
        if not isinstance(item, dict):
            # Une entrée qui n'est pas un objet ne porte ni score ni numéro exploitable.
            en_attente.append({})
            continue
        rang = _rank(item.get("id"), taille)
        if rang is not None and par_rang[rang] is None:
            par_rang[rang] = item
        else:
            en_attente.append(item)

    if en_attente:
        logger.warning(
            "Scoring : %d note(s) au numéro illisible ou dupliqué, rattachée(s) par ordre",
            len(en_attente),
        )
    libres = [rang for rang, item in enumerate(par_rang) if item is None]
    for rang, item in zip(libres, en_attente):
        par_rang[rang] = item
    if len(en_attente) > len(libres):
        # Le modèle a rendu plus de notes que d'articles envoyés : les surnuméraires
        # n'ont personne à qui se rattacher, et les inventer serait pire que les jeter.
        logger.warning(
            "Scoring : %d note(s) en trop pour %d article(s), ignorée(s)",
            len(en_attente) - len(libres),
            taille,
        )

    return [item or {} for item in par_rang]


def _rank(value: Any, taille: int) -> int | None:
    """Numéro envoyé au modèle (1 à N) ramené en index, None s'il est inexploitable."""
    try:
        rang = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return rang - 1 if 1 <= rang <= taille else None


EXEMPLES: list[dict] = [
    {
        "id": "demo-1",
        "title": "L'ANSSI publie la version 3.3 du référentiel SecNumCloud",
        "summary": (
            "Le référentiel SecNumCloud évolue avec de nouvelles exigences sur la "
            "localisation des données et l'immunité aux législations extraterritoriales. "
            "Les prestataires qualifiés disposent de dix-huit mois pour se mettre en conformité."
        ),
        "source": "ANSSI",
        "url": "https://example.org/secnumcloud-3-3",
        "content": (
            "L'ANSSI a publié la version 3.3 du référentiel SecNumCloud. Les évolutions "
            "portent sur trois axes. Premièrement, le renforcement des exigences de "
            "localisation : les données comme les métadonnées d'exploitation doivent résider "
            "sur le territoire de l'Union européenne, opérées par une entité immunisée aux "
            "législations extraterritoriales. Deuxièmement, la gestion des clés de "
            "chiffrement, qui doit désormais relever exclusivement du client ou d'un tiers de "
            "confiance qualifié. Troisièmement, un durcissement des exigences de "
            "journalisation et de conservation des traces. Les prestataires déjà qualifiés "
            "disposent d'une période de transition de dix-huit mois."
        ),
    },
    {
        "id": "demo-2",
        "title": "Nouvelle génération de smartphones pliables annoncée",
        "summary": "Un constructeur dévoile son modèle pliable doté d'un écran plus lumineux.",
        "source": "Blog Tech",
        "url": "https://example.org/pliables",
    },
    {
        "id": "demo-3",
        "title": "CVE-2026-0000 : exécution de code à distance dans une librairie de chiffrement",
        # Résumé vide : le cas qui ne doit pas faire planter le scoring.
        "summary": "",
        "source": "CERT-FR",
        "url": "https://example.org/cve-2026-0000",
        "content": (
            "Une vulnérabilité critique affecte une bibliothèque de chiffrement largement "
            "utilisée dans les chaînes de traitement de fichiers. Un défaut de validation de "
            "longueur lors du déchiffrement de conteneurs permet de provoquer un débordement "
            "de tampon aboutissant à une exécution de code à distance. La vulnérabilité est "
            "déclenchable par un fichier fourni par un utilisateur non authentifié, ce qui "
            "expose particulièrement les services de dépôt et de partage de fichiers. Un "
            "correctif est disponible et le CERT-FR recommande une mise à jour immédiate."
        ),
    },
]


def _demo() -> None:
    """Scoring puis résumé sur les trois articles ci-dessus, via le fournisseur configuré."""
    # Import local : `llm` importe ce module, le charger en tête ferait un cycle.
    from rssresume import llm
    from rssresume.llm.providers import ARTICLE, SCORING

    noteur = llm.for_action(SCORING)
    if noteur is None:
        raise SystemExit(
            "Aucune clé d'API pour le fournisseur de notation. "
            "Définir OPENAI_API_KEY (ou MISTRAL_API_KEY, selon RSSRESUME_PROVIDER)."
        )

    notes = noteur.score_articles(EXEMPLES)
    for note in notes:
        print(f"[{note['score']:>2}/10] {note['thematique']:<13} {note['id']} — {note['angle']}")

    print()
    par_id = {str(a["id"]): a for a in EXEMPLES}
    resumeur = llm.for_action(ARTICLE) or noteur
    for item in select(notes, set(par_id), seuil=7, max_items=12):
        article = par_id[str(item["id"])]
        if not full_text(article):
            # Ni contenu ni résumé : inutile de dépenser un appel pour du vide.
            logger.warning("Résumé : article %s sans texte, ignoré", item["id"])
            continue
        print(f"--- {article['title']} ({article.get('source')}, {item['score']}/10)")
        print(resumeur.summarize_article(article))
        print(article.get("url"))
        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()
