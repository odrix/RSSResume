"""Les réglages d'un fournisseur, lus dans `providers.json`.

Ce module ne fait qu'une chose : rendre un `Settings` — un objet de valeurs, sans
comportement, qu'on injecte dans un `LLMProvider`. Tout ce qui n'est pas un secret
vient du JSON ; l'environnement ne porte que la clé d'API et le choix du fournisseur.

    settings("mistral").voice.voice   -> "fr_marie_curious"
    settings("openai").call("digest") -> Call(model="gpt-5.6-luna", effort="medium", …)
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import json
import os
import pathlib

#: Les actions qu'un fournisseur sait rendre. Ce sont aussi les postes du journal.
SCORING = "scoring"
ARTICLE = "article"
DIGEST = "digest"
#: L'éphéméride d'ouverture : un appel par journée, pas un par catégorie.
EPHEMERIDE = "ephemeride"
#: Le montage de la journée en un seul texte, quand l'audio est global. Un appel par
#: journée lui aussi, et seulement dans ce mode — il n'est pas payé en mode `category`.
MONTAGE = "montage"
TTS = "tts"
ACTIONS = (SCORING, ARTICLE, DIGEST, EPHEMERIDE, MONTAGE, TTS)

#: Le fournisseur retenu quand rien ne le dit.
DEFAULT_PROVIDER = "openai"

#: Choix du fournisseur : `RSSRESUME_PROVIDER` pour tout, `RSSRESUME_<ACTION>_PROVIDER`
#: pour une action seule. La clé d'API, elle, se nomme d'après le fournisseur.
ENV_PROVIDER = "RSSRESUME_PROVIDER"
ENV_PROVIDER_TEMPLATE = "RSSRESUME_{action}_PROVIDER"
ENV_API_KEY_TEMPLATE = "{provider}_API_KEY"
ENV_PROVIDERS_FILE = "RSSRESUME_PROVIDERS_FILE"

BUILTIN_PATH = pathlib.Path(__file__).with_name("providers.json")


class ProviderError(RuntimeError):
    """Fournisseur inconnu, action non déclarée, ou table illisible."""


@dataclasses.dataclass(frozen=True)
class Call:
    """Réglages d'une action de complétion chez un fournisseur.

    `effort` ne vaut que pour les modèles raisonnants d'OpenAI ; les fournisseurs qui
    l'ignorent ne le déclarent simplement pas. Un `max_tokens` à None laisse le plafond
    du fournisseur — chez un modèle raisonnant, ce plafond inclut les tokens de
    raisonnement, absents de la réponse, et se règle donc plus large qu'il n'y paraît.
    """

    action: str
    model: str
    temperature: float = 0.4
    max_tokens: int | None = None
    effort: str | None = None


@dataclasses.dataclass(frozen=True)
class Voice:
    """Réglages de la synthèse vocale.

    `instructions` dirige la diction chez les fournisseurs qui ont un champ pour la
    recevoir ; les autres ne la déclarent pas, et le champ reste vide.
    """

    model: str
    voice: str
    audio_format: str = "mp3"
    instructions: str | None = None
    #: Plafond d'entrée de l'endpoint de synthèse, en caractères. Au-delà, le texte est
    #: découpé et les audios raboutés (`audio.py`). `None` quand le fournisseur n'en
    #: déclare pas : le texte part alors d'un seul tenant, comme avant.
    input_limit: int | None = None


@dataclasses.dataclass(frozen=True)
class Settings:
    """Tout ce qu'un fournisseur sait de lui-même, prêt à être injecté."""

    name: str
    label: str
    base_url: str
    api_key: str | None
    calls: dict[str, Call]
    voice: Voice
    prices: dict[str, dict[str, float]]

    @property
    def configured(self) -> bool:
        """Vrai si l'appel est possible : une URL et une clé."""
        return bool(self.base_url and self.api_key)

    def call(self, action: str) -> Call:
        try:
            return self.calls[action]
        except KeyError:
            raise ProviderError(
                f"Le fournisseur '{self.name}' ne déclare pas l'action '{action}' "
                f"(déclarées : {', '.join(sorted(self.calls)) or 'aucune'})."
            ) from None


# -- lecture de la table ----------------------------------------------------


def _read(path: pathlib.Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Table de fournisseurs illisible ({path}) : {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError(f"Table de fournisseurs illisible ({path}) : objet JSON attendu.")
    # Les clés qui commencent par `_` sont des commentaires, pas des fournisseurs.
    return {name: block for name, block in parsed.items() if not name.startswith("_")}


def _merge(base: dict, overlay: dict) -> dict:
    """Fusion en profondeur : un fichier externe ne redéclare que ce qu'il change."""
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@functools.lru_cache(maxsize=8)
def _table(external: str | None) -> dict:
    """Table brute, JSON livré plus fichier externe. En cache : elle ne bouge pas."""
    table = _read(BUILTIN_PATH)
    return _merge(table, _read(pathlib.Path(external))) if external else table


def _env(name: str) -> str | None:
    return (os.getenv(name) or "").strip() or None


def _num(block: dict, key: str, default=None):
    value = block.get(key, default)
    return value if isinstance(value, (int, float)) else default


def table() -> dict:
    """La table des fournisseurs, telle que le JSON la donne."""
    return _table(_env(ENV_PROVIDERS_FILE))


def names() -> list[str]:
    return sorted(table())


def settings(name: str | None = None) -> Settings:
    """Les réglages d'un fournisseur, clé d'API comprise."""
    name = (name or DEFAULT_PROVIDER).strip().lower()
    block = table().get(name)
    if block is None:
        raise ProviderError(
            f"Fournisseur inconnu : '{name}'. Déclarés : {', '.join(names()) or 'aucun'}. "
            f"En ajouter un se fait dans providers.json, ou dans {ENV_PROVIDERS_FILE}."
        )
    tts = block.get("tts") or {}
    return Settings(
        name=name,
        label=str(block.get("label") or name),
        base_url=str(block.get("base_url") or "").rstrip("/"),
        api_key=_env(ENV_API_KEY_TEMPLATE.format(provider=name.upper())),
        calls={
            action: Call(
                action=action,
                model=str(reglages.get("model") or ""),
                temperature=float(_num(reglages, "temperature", 0.4)),
                max_tokens=(
                    int(_num(reglages, "max_tokens"))
                    if _num(reglages, "max_tokens") is not None
                    else None
                ),
                effort=(str(reglages["effort"]) if reglages.get("effort") else None),
            )
            for action, reglages in (block.get("actions") or {}).items()
        },
        voice=Voice(
            model=str(tts.get("model") or ""),
            voice=str(tts.get("voice") or ""),
            audio_format=str(tts.get("format") or "mp3").lstrip("."),
            instructions=(str(tts["instructions"]).strip() or None)
            if tts.get("instructions")
            else None,
            input_limit=(
                int(_num(tts, "input_limit")) if _num(tts, "input_limit") else None
            ),
        ),
        prices={
            str(model): {str(k): float(v) for k, v in tarif.items() if isinstance(v, (int, float))}
            for model, tarif in (block.get("prices") or {}).items()
            if isinstance(tarif, dict)
        },
    )


def chosen(action: str) -> str:
    """Le fournisseur d'une action : le sien, celui de toutes, ou le défaut."""
    return (
        _env(ENV_PROVIDER_TEMPLATE.format(action=action.upper()))
        or _env(ENV_PROVIDER)
        or DEFAULT_PROVIDER
    ).lower()


def all_prices() -> dict[str, dict[str, float]]:
    """Les tarifs de tous les fournisseurs, à plat, pour `pricing.py`."""
    prices: dict[str, dict[str, float]] = {}
    for name in names():
        prices.update(settings(name).prices)
    return prices


def describe() -> dict:
    """Qui fait quoi dans cette exécution, pour le journal.

    Décrit l'environnement et non les objets injectés : c'est bien le réglage lu au
    lancement que le journal doit fixer, pour que deux journaux se comparent.
    """
    vu: dict = {}
    for action in ACTIONS:
        reglages = settings(chosen(action))
        entree = {"fournisseur": reglages.name, "actif": reglages.configured}
        if action == TTS:
            entree["modele"] = reglages.voice.model
            entree["voix"] = reglages.voice.voice
        else:
            try:
                entree["modele"] = reglages.call(action).model
            except ProviderError:
                # Un fichier externe (`RSSRESUME_PROVIDERS_FILE`) peut décrire un
                # fournisseur qui ignore une action ajoutée depuis. Le journal le dit
                # au lieu de faire échouer la journée sur sa propre description.
                entree["modele"] = None
                entree["actif"] = False
            vu[action] = entree
            continue
        vu[action] = entree
    return vu
