"""Réessai des appels réseau, partagé par tout ce qui sort de la machine.

Le digest est un travail nocturne que personne ne regarde : un 429 du fournisseur ou un
502 devant FreshRSS suffisait à ce que la journée n'existe pas. Trois tentatives, un
délai qui double, et un peu de hasard pour ne pas repartir pile au même instant qu'un
autre client — à une exécution par jour, c'est tout ce que la résilience demande, et
c'est vingt lignes plutôt qu'une passerelle de plus à exploiter.

Ce module ne connaît ni FreshRSS ni les fournisseurs de LLM : il reçoit un appel à
tenter et le rejoue. D'où sa testabilité sans réseau — une doublure qui échoue N fois
avant de réussir suffit à le juger.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import logging
import random
import time
import urllib.error
from typing import Callable

from rssresume.tools import console

logger = logging.getLogger(__name__)

#: Trois tentatives : la première, puis deux reprises.
ATTEMPTS = 3
#: Délai de la première reprise, doublé à chaque suivante.
BASE_DELAY = 1.0
#: Plafond d'attente. Au-delà, mieux vaut rendre la main : la catégorie suivante attend,
#: et un fournisseur qui demande plus que ça ne sera pas rétabli dans la minute.
MAX_DELAY = 30.0
#: Les codes qui valent d'être rejoués : 429 pour le quota, 5xx pour le serveur d'en face.
#: Tout autre 4xx vient de nous — même requête, même réponse : la rejouer ne fait que perdre
#: du temps et, sur un edit-tag, risquerait de réécrire ce qui a déjà été écrit.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
#: Ce que la machine annonce en sortant. Sans lui, `urllib` signe « Python-urllib/3.x »,
#: signature que les pare-feux applicatifs bannissent : les sites d'éditeurs rendent un
#: 403, et Cloudflare — devant l'API de Resend, entre autres — un « error code: 1010 »
#: qui ne ressemble à rien de ce que le service documente. Un nom honnête suffit à passer.
USER_AGENT = "Mozilla/5.0 (compatible; RSSResume/1.0)"


def retry[T](
    operation: Callable[[], T],
    label: str,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Exécute `operation`, et la rejoue tant que l'échec est réputé passager.

    `sleep` est résolu à l'appel et non à la définition : c'est ce qui laisse un test
    remplacer l'attente sans patcher `time` pour tout le processus.

    L'exception d'origine ressort intacte quand les tentatives sont épuisées ou que
    l'échec ne se rejoue pas : c'est l'appelant qui sait la traduire — `LLMError` chez
    un fournisseur, `RuntimeError` côté FreshRSS — et il ne doit pas avoir à démêler
    une erreur de transport d'une erreur de réessai.
    """
    for tentative in range(1, attempts + 1):
        try:
            return operation()
        except OSError as exc:  # `URLError` et `HTTPError` en héritent, `TimeoutError` aussi.
            delai = _delay(exc, tentative)
            if delai is None or tentative == attempts:
                raise
            console.detail(
                f"{label} : {_reason(exc)}, nouvelle tentative dans {delai:.1f}s "
                f"({tentative}/{attempts})"
            )
            logger.warning(
                "%s : tentative %d/%d échouée (%s), reprise dans %.1fs",
                label,
                tentative,
                attempts,
                _reason(exc),
                delai,
            )
            (sleep or time.sleep)(delai)
    # Inatteignable : la boucle rend ou lève. Présent pour les relecteurs de types.
    raise RuntimeError(f"{label} : aucune tentative exécutée")


def _delay(exc: OSError, tentative: int) -> float | None:
    """Le délai avant la reprise, `None` quand l'échec ne se rejoue pas.

    Un serveur qui dit lui-même quand revenir a toujours raison contre notre backoff :
    c'est lui qui connaît la fenêtre de son quota.
    """
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code not in RETRYABLE_STATUS:
            return None
        demande = _retry_after(exc)
        if demande is not None:
            return min(max(demande, 0.0), MAX_DELAY)
    return _backoff(tentative)


def _backoff(tentative: int) -> float:
    """Exponentiel, à moitié tiré au sort : deux clients tombés ensemble ne reviennent pas ensemble."""
    plafond = min(BASE_DELAY * 2 ** (tentative - 1), MAX_DELAY)
    return plafond * (0.5 + random.random() / 2)


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """L'en-tête `Retry-After`, en secondes. La norme autorise un délai ou une date."""
    brut = (exc.headers.get("Retry-After") if exc.headers else None) or ""
    brut = brut.strip()
    if not brut:
        return None
    try:
        return float(brut)
    except ValueError:
        pass
    try:
        date = email.utils.parsedate_to_datetime(brut)
    except (TypeError, ValueError):
        # En-tête illisible : le backoff reprend la main plutôt que de faire échouer l'appel.
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    return (date - dt.datetime.now(dt.timezone.utc)).total_seconds()


def _reason(exc: OSError) -> str:
    """L'échec en quelques mots, pour la console et les logs."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"connexion impossible ({exc.reason})"
    return f"{type(exc).__name__} ({exc})"
