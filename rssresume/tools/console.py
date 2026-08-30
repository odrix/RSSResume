"""Suivi de l'exécution affiché dans la console.

Trois niveaux de message pour garder une sortie lisible :

    RSSResume : digest du 2026-08-23        -> log()
    [Tech] 5 article(s)                     -> category()
      résumé via gpt-4o-mini                -> detail()

Ce qui a échoué sort sur l'erreur standard -> error(). Les agrégateurs de logs — Dokploy
en tête — classent par flux et non par contenu : un échec écrit sur la sortie standard
s'affiche en « info » au milieu du reste, et un matin sans digest ne se remarque pas.
"""

from __future__ import annotations

import sys

_enabled = True


def enable(value: bool = True) -> None:
    """Active ou coupe la sortie (les tests la coupent)."""
    global _enabled
    _enabled = value


def log(message: str) -> None:
    if _enabled:
        print(message, flush=True)


def error(message: str) -> None:
    """Un échec, sur l'erreur standard : c'est là que les agrégateurs le lisent."""
    if _enabled:
        print(message, file=sys.stderr, flush=True)


def category(name: str, message: str) -> None:
    log(f"[{name}] {message}")


def detail(message: str) -> None:
    log(f"  {message}")
