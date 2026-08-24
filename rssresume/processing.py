"""Scoring de pertinence puis résumé des articles retenus, via une API OpenAI-compatible.

Deux étapes volontairement asymétriques :
- `score_articles` ne voit que titre + résumé court, mais passe sur tout le lot ;
- `summarize_top` ne voit que les articles retenus, mais en texte intégral.

Le transport est celui du reste du projet (`rssresume.llm`), mais la configuration est
lue directement dans l'environnement : le module reste utilisable sans FreshRSS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from rssresume import llm

logger = logging.getLogger(__name__)

#: Taille de lot pour le scoring : au-delà, le modèle survole et la fin du lot se dégrade.
#: À changer en même temps que `llm.SCORING.max_tokens`, qui la dimensionne.
SCORING_BATCH_SIZE = 40

THEMATIQUES = ("reglementaire", "cyber", "marche", "stack", "autre")
DEFAULT_THEMATIQUE = "autre"

PROFIL = """CTO d'un SaaS B2B français de stockage, partage et transfert de fichiers
sécurisé. Infrastructure hébergée en France, qualifiée SecNumCloud, produit certifié
CSPN par l'ANSSI.

Axes de veille pertinents :
- reglementaire : souveraineté et conformité (SecNumCloud, EUCS, NIS2, DORA, RGPD,
  doctrine ANSSI, Cloud Act / FISA, décisions CNIL).
- cyber : cybersécurité technique (CVE exploitables, chiffrement, gestion de clés,
  crypto post-quantique, chaîne d'approvisionnement logicielle, incidents majeurs).
- marche : marché et concurrence (acteurs du transfert de fichiers sécurisé et du
  cloud souverain français ou européen, levées, rachats, appels d'offres publics).
- stack : veille technologique sur la stack d'un SaaS de ce type (stockage objet,
  chiffrement de bout en bout, performance de transfert, observabilité, coûts cloud).

Ne sont PAS pertinents : l'actualité IA grand public, les levées de fonds hors de ce
marché, le hardware grand public, les annonces produit sans impact technique ou
réglementaire pour cet éditeur."""

SCORING_SYSTEM = (
    "Tu assistes la veille quotidienne d'un décideur technique. Voici son profil, "
    "qui est le SEUL critère de pertinence :\n\n"
    + PROFIL
    + "\n\n"
    + """Tu reçois une liste d'articles (id, titre, résumé court). Pour CHAQUE article tu produis :
- "score" : entier de 0 à 10 selon le barème ci-dessous ;
- "thematique" : exactement une valeur parmi reglementaire, cyber, marche, stack, autre ;
- "angle" : UNE phrase expliquant en quoi l'article compte (ou non) pour ce profil précis.

Barème :
0-2  hors sujet pour ce profil
3-4  connexe, mais sans conséquence pour lui
5-6  intéressant à connaître, non actionnable
7-8  pertinent, à lire aujourd'hui
9-10 critique ou directement actionnable (obligation réglementaire, faille sur sa stack,
     mouvement d'un concurrent direct)

Règles impératives :
- Traite TOUS les articles reçus, sans exception ni échantillonnage. Un article hors sujet
  reçoit un score bas, il n'est jamais omis.
- Renvoie exactement autant d'objets que d'articles reçus, dans le même ordre, en reprenant
  l'id d'origine à l'identique.
- Un résumé vide n'est pas une raison d'omettre l'article : juge alors sur le seul titre.
- Réponds UNIQUEMENT par du JSON valide, sans texte avant ni après, sans balises Markdown.

Format JSON exact attendu :
{"resultats": [{"id": "...", "score": 0, "thematique": "...", "angle": "..."}]}"""
)

SUMMARY_SYSTEM = (
    "Tu résumes des articles de veille pour un décideur technique. Voici son profil :\n\n"
    + PROFIL
    + "\n\n"
    + """Tu reçois un article en texte intégral. Rends un résumé de 3 à 4 phrases, en français,
qui privilégie ce qui a des conséquences concrètes pour ce profil : ce qui change, à quelle
échéance, et ce que cela implique pour lui.

Règles :
- 3 à 4 phrases, pas davantage. Pas de liste à puces, pas de titre.
- Aucune formule d'introduction du type "Voici le résumé" ou "Cet article traite de".
- Rends le résumé seul, sans commentaire ni balise Markdown."""
)


def scoring_prompt_digest() -> str:
    """Empreinte courte du prompt de scoring, modèle compris.

    Sert de clé de cache : tant qu'elle ne change pas, un article déjà noté n'est pas
    renoté. Toute retouche de PROFIL, du barème ou du modèle produit une empreinte
    différente et déclenche donc la renotation.
    """
    material = f"{SCORING_SYSTEM}\n{llm.SCORING.model}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


class ProcessingError(RuntimeError):
    """Réponse du modèle inexploitable : JSON invalide ou lot incomplet.

    Les échecs propres au fournisseur (HTTP, réponse tronquée) remontent en `llm.LLMError`.
    """


Credentials = tuple[str, str]


def _call(
    system: str,
    user: str,
    profile: llm.ChatProfile,
    credentials: Credentials | None = None,
) -> str:
    """Un appel au fournisseur ; renvoie le texte de la réponse."""
    base_url, api_key = credentials or llm.credentials_from_env()
    return llm.chat(base_url, api_key, profile, system, user)


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


def _score_batch(batch: list[dict], credentials: Credentials | None = None) -> list[dict]:
    """Score un lot en un seul appel, et vérifie qu'aucun article n'a été perdu."""
    payload = [
        {
            "id": str(article["id"]),
            "titre": article.get("title") or "",
            # Un résumé absent est fréquent : on l'explicite plutôt que d'envoyer du vide.
            "resume": (article.get("summary") or "").strip() or "(aucun résumé fourni)",
        }
        for article in batch
    ]
    raw = _call(
        SCORING_SYSTEM,
        f"{len(payload)} articles à évaluer :\n\n{json.dumps(payload, ensure_ascii=False)}",
        llm.SCORING,
        credentials,
    )
    resultats = _resultats(_extract_json(raw))

    if len(resultats) != len(batch):
        raise ProcessingError(
            f"Lot incomplet : {len(batch)} article(s) envoyé(s), {len(resultats)} noté(s)."
        )

    par_id = {str(item.get("id")): item for item in resultats}
    manquants = [str(article["id"]) for article in batch if str(article["id"]) not in par_id]
    if manquants:
        raise ProcessingError(f"Identifiants absents de la réponse : {manquants[:5]}")

    return [
        {
            "id": str(article["id"]),
            "score": _clean_score(par_id[str(article["id"])].get("score")),
            "thematique": _clean_thematique(par_id[str(article["id"])].get("thematique")),
            "angle": str(par_id[str(article["id"])].get("angle") or "").strip(),
        }
        for article in batch
    ]


def score_articles(articles: list[dict], credentials: Credentials | None = None) -> list[dict]:
    """Note la pertinence de chaque article, sur titre + résumé court uniquement.

    Renvoie un dict {id, score, thematique, angle} par article d'entrée, dans le même ordre.
    """
    logger.info("Scoring : %d article(s) en entrée", len(articles))
    if not articles:
        return []

    scored: list[dict] = []
    for start in range(0, len(articles), SCORING_BATCH_SIZE):
        batch = articles[start : start + SCORING_BATCH_SIZE]
        logger.info(
            "Scoring : lot %d, articles %d à %d",
            start // SCORING_BATCH_SIZE + 1,
            start + 1,
            start + len(batch),
        )
        scored.extend(_score_batch(batch, credentials))

    if len(scored) != len(articles):
        raise ProcessingError(f"Scoring incomplet : {len(articles)} entrées, {len(scored)} sorties.")

    logger.info("Scoring : %d article(s) en sortie", len(scored))
    return scored


def _full_text(article: dict) -> str:
    """Texte intégral si disponible, résumé court sinon."""
    return (article.get("content") or "").strip() or (article.get("summary") or "").strip()


def summarize_top(
    articles: list[dict],
    scored: list[dict],
    seuil: int = 7,
    max_items: int = 12,
    credentials: Credentials | None = None,
) -> list[dict]:
    """Résume en texte intégral les articles dont le score atteint le seuil.

    Renvoie {id, title, url, source, thematique, score, resume} par article retenu,
    trié par score décroissant et plafonné à `max_items`.
    """
    logger.info("Sélection : %d article(s), seuil %d, plafond %d", len(articles), seuil, max_items)
    par_id = {str(article["id"]): article for article in articles}

    retenus = sorted(
        (item for item in scored if item["score"] >= seuil and str(item["id"]) in par_id),
        key=lambda item: item["score"],
        reverse=True,
    )
    logger.info("Sélection : %d article(s) au-dessus du seuil", len(retenus))

    retenus = retenus[:max_items]
    logger.info("Résumé : %d article(s) à résumer", len(retenus))

    resumes: list[dict] = []
    for rang, item in enumerate(retenus, start=1):
        article = par_id[str(item["id"])]
        texte = _full_text(article)
        titre = article.get("title") or ""
        if not texte:
            # Ni contenu ni résumé : inutile de dépenser un appel pour du vide.
            logger.warning("Résumé : article %s sans texte, ignoré", item["id"])
            continue

        logger.info("Résumé : %d/%d — %s", rang, len(retenus), titre[:70])
        resume = _call(
            SUMMARY_SYSTEM,
            f"Titre : {titre}\nSource : {article.get('source') or 'inconnue'}\n\n{texte}",
            llm.ARTICLE_SUMMARY,
            credentials,
        )
        resumes.append(
            {
                "id": str(item["id"]),
                "title": titre,
                "url": article.get("url") or "",
                "source": article.get("source") or "",
                "thematique": item["thematique"],
                "score": item["score"],
                "resume": resume,
            }
        )

    logger.info("Résumé : %d article(s) en sortie", len(resumes))
    return resumes


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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    notes = score_articles(EXEMPLES)
    for note in notes:
        print(f"[{note['score']:>2}/10] {note['thematique']:<13} {note['id']} — {note['angle']}")

    print()
    for resume in summarize_top(EXEMPLES, notes, seuil=7, max_items=12):
        print(f"--- {resume['title']} ({resume['source']}, {resume['score']}/10)")
        print(resume["resume"])
        print(resume["url"], "\n")
