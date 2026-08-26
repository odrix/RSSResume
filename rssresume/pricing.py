"""Tarifs des appels aux fournisseurs, et calcul du coût d'un appel.

Un appel facturé n'est jamais renvoyé avec son prix : le fournisseur rend des
compteurs de tokens, la conversion en euros ou en dollars est à notre charge.
Ce module est donc une multiplication, et un point de lecture pour une table de
prix qu'il ne détient pas : elle vit dans `providers.json`, sous chaque
fournisseur, à côté des modèles qu'elle tarife. Ajouter un fournisseur, c'est
donc aussi lui donner ses prix, au même endroit et sans toucher au code.

Deux formes de tarif, unifiées sous la même clé de modèle :

- ``{"input": x, "output": y}`` — dollars par million de tokens. Un tarif sans
  ``output`` (les modèles de synthèse vocale récents) ne facture que l'entrée.
- ``{"characters": z}`` — dollars par million de caractères, la facturation
  au caractère de la synthèse vocale.

Un modèle absent de la table ne produit pas un coût faux : il produit ``None``,
et le journal le signale comme non tarifé. La table se complète sans toucher au
paquet par ``RSSRESUME_PROVIDERS_FILE`` (le bloc ``prices`` d'un fournisseur) ou,
pour un tarif isolé, par ``RSSRESUME_PRICES``, un objet JSON du même format
fusionné par-dessus tous les fournisseurs.
"""

from __future__ import annotations

import json
import os
import re

from rssresume.llm import providers

#: Devise des tarifs, celle des grilles publiées par les fournisseurs.
CURRENCY = "USD"

#: Les tarifs sont exprimés par million d'unités : c'est la forme publiée, et la
#: garder évite d'écrire des prix à six zéros après la virgule.
PER = 1_000_000

#: Estimation tokens ↔ caractères pour la synthèse vocale, qui est facturée au
#: token d'entrée mais n'en rend aucun compteur. Le rapport vaut pour du français
#: comme pour de l'anglais à un cheveu près ; le coût TTS est donc *estimé*, et le
#: journal le dit.
CHARS_PER_TOKEN = 4


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


def prices() -> dict[str, dict[str, float]]:
    """Grille de tous les fournisseurs déclarés, `RSSRESUME_PRICES` par-dessus.

    Relue à chaque appel : `RSSRESUME_PROVIDERS_FILE` comme `RSSRESUME_PRICES`
    peuvent nommer un modèle que la grille livrée ignore, et le journal d'une
    exécution doit refléter l'environnement de cette exécution.
    """
    return {**providers.all_prices(), **_overrides()}


def tarif(model: str) -> dict[str, float] | None:
    """Tarif d'un modèle, `None` s'il est inconnu.

    Le nom exact d'abord, puis — et seulement — le même nom suivi d'un instantané
    daté : lister toutes les dates de publication serait intenable, et elles ne
    changent pas le prix. Un suffixe qui n'est pas une date n'est pas rattaché,
    même s'il commence par un modèle connu : `gpt-5.6-luna` commence par `gpt-5`
    sans être `gpt-5`, et le prix rendu serait faux sans que rien ne le signale.
    Un modèle non tarifé se déclare dans le bloc `prices` de son fournisseur,
    ou dans `RSSRESUME_PRICES`.
    """
    name = (model or "").strip().lower()
    if not name:
        return None
    table = prices()
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
