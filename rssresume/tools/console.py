"""Suivi de l'exécution affiché dans la console.

Trois niveaux de message pour garder une sortie lisible :

    RSSResume : digest du 2026-08-23        -> log()
    [Tech] 5 article(s)                     -> category()
      résumé via gpt-4o-mini                -> detail()
"""

from __future__ import annotations

_enabled = True


def enable(value: bool = True) -> None:
    """Active ou coupe la sortie (les tests la coupent)."""
    global _enabled
    _enabled = value


def log(message: str) -> None:
    if _enabled:
        print(message, flush=True)


def category(name: str, message: str) -> None:
    log(f"[{name}] {message}")


def detail(message: str) -> None:
    log(f"  {message}")
