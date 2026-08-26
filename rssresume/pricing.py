"""Tarifs des appels au fournisseur, et calcul du coût d'un appel.

Un appel facturé n'est jamais renvoyé avec son prix : le fournisseur rend des
compteurs de tokens, la conversion en euros ou en dollars est à notre charge.
Ce module est donc une table de prix, forcément datée, et une multiplication.

Deux formes de tarif, unifiées sous la même clé de modèle :

- ``{"input": x, "output": y}`` — dollars par million de tokens. Un tarif sans
  ``output`` (les modèles de synthèse vocale récents) ne facture que l'entrée.
- ``{"characters": z}`` — dollars par million de caractères, la facturation
  historique de la synthèse vocale.

Un modèle absent de la table ne produit pas un coût faux : il produit ``None``,
et le journal le signale comme non tarifé. La table se complète sans toucher au
code par ``RSSRESUME_PRICES``, un objet JSON du même format fusionné par-dessus.
"""

from __future__ import annotations

import json
import os
import re

#: Devise des tarifs ci-dessous, celle des grilles publiées par les fournisseurs.
CURRENCY = "USD"

#: Les tarifs sont exprimés par million d'unités : c'est la forme publiée, et la
#: garder évite d'écrire des prix à six zéros après la virgule.
PER = 1_000_000

#: Estimation tokens ↔ caractères pour la synthèse vocale, qui est facturée au
#: token d'entrée mais n'en rend aucun compteur. Le rapport vaut pour du français
#: comme pour de l'anglais à un cheveu près ; le coût TTS est donc *estimé*, et le
#: journal le dit.
CHARS_PER_TOKEN = 4

#: Grille au 2026-05, en dollars par million d'unités. À revérifier : les prix
#: baissent, et un tarif périmé ici se lit comme un coût réel dans les journaux.
PRICES: dict[str, dict[str, float]] = {
    # Complétion — dollars par million de tokens.
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-5": {"input": 1.25, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 1.10, "output": 4.40},
    "o3": {"input": 2.00, "output": 8.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Synthèse vocale — au caractère pour les modèles historiques, au token
    # d'entrée pour les suivants.
    "tts-1": {"characters": 15.00},
    "tts-1-hd": {"characters": 30.00},
    "gpt-4o-mini-tts": {"input": 0.60},
}

#: Variable d'environnement qui complète ou corrige la table, au même format JSON.
PRICES_ENV = "RSSRESUME_PRICES"

#: Suffixe d'instantané daté, la seule chose qu'un nom de modèle peut porter en plus
#: sans changer de tarif : `gpt-4o-mini-2024-07-18`, `gpt-4o-2024-11-20`, `-0613`.
#: Tout autre suffixe désigne un AUTRE modèle — `gpt-5.6-luna` n'est pas `gpt-5`, et le
#: facturer au tarif de `gpt-5` produirait un coût faux, plus nuisible qu'un coût absent.
SNAPSHOT_SUFFIX = re.compile(r"^-\d{4}(-\d{2}-\d{2})?$")


def _overrides() -> dict[str, dict[str, float]]:
    """Tarifs supplémentaires lus dans l'environnement, ignorés s'ils sont illisibles.

    Un JSON de configuration mal formé ne doit pas faire échouer une exécution de
    veille : le journal signalera simplement des modèles non tarifés.
    """
    raw = (os.getenv(PRICES_ENV) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(model): {str(k): float(v) for k, v in tarif.items() if isinstance(v, (int, float))}
        for model, tarif in parsed.items()
        if isinstance(tarif, dict)
    }


def tarif(model: str) -> dict[str, float] | None:
    """Tarif d'un modèle, `None` s'il est inconnu.

    Le nom exact d'abord, puis — et seulement — le même nom suivi d'un instantané
    daté : lister toutes les dates de publication serait intenable, et elles ne
    changent pas le prix. Un suffixe qui n'est pas une date n'est pas rattaché,
    même s'il commence par un modèle connu : `gpt-5.6-luna` commence par `gpt-5`
    sans être `gpt-5`, et le prix rendu serait faux sans que rien ne le signale.
    Un modèle non tarifé se déclare dans `RSSRESUME_PRICES`.
    """
    name = (model or "").strip().lower()
    if not name:
        return None
    table = {**PRICES, **_overrides()}
    if name in table:
        return table[name]
    candidats = [key for key in table if SNAPSHOT_SUFFIX.match(name[len(key) :])]
    return table[max(candidats, key=len)] if candidats else None


def cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    characters: int = 0,
) -> float | None:
    """Coût d'un appel en dollars, `None` si le modèle n'est pas tarifé.

    Un tarif au caractère ignore les tokens, et réciproquement : les deux formes
    ne se mélangent jamais dans une même grille.
    """
    prix = tarif(model)
    if prix is None:
        return None
    if "characters" in prix:
        return characters / PER * prix["characters"]
    return (
        input_tokens / PER * prix.get("input", 0.0)
        + output_tokens / PER * prix.get("output", 0.0)
    )


def tokens_from_characters(characters: int) -> int:
    """Tokens d'entrée estimés pour un texte de synthèse vocale."""
    return round(characters / CHARS_PER_TOKEN)
