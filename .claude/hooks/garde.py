"""Garde-fous de session Claude Code, appelés par les hooks de .claude/settings.json.

Les règles du CLAUDE.md (pas d'édition au shell, pas de .env, suite verte avant de rendre
la main) étaient des consignes à retenir ; elles ont déjà été oubliées une fois, au prix
d'un dépôt entier réécrit en LF. Un hook ne s'oublie pas.

Trois points d'entrée, choisis par le premier argument :

- ``pre``  : PreToolUse, refuse l'appel (code 2) s'il enfreint une règle ;
- ``post`` : PostToolUse sur Edit/Write, relance la suite quand un ``.py`` a changé, pour
  voir la régression au moment où elle entre et non en fin de tâche ;
- ``stop`` : Stop, interdit de conclure sur une suite rouge si du Python a bougé.

Le code de sortie 2 est le seul que Claude Code renvoie au modèle comme un refus : le
message part sur stderr. Bibliothèque standard seule, comme le reste du projet.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# `.env` et `.env.local`, mais ni `.env.example` ni `os.environ` ni `.envrc`.
ENV_PRIVE = re.compile(r"(?<![\w.])\.env(?:\.local)?(?![\w.])")

SED_EN_PLACE = re.compile(r"\bsed\b[^|;&]*\s(?:-[a-zA-Z]*i|--in-place)")
HEREDOC = re.compile(r"<<-?\s*['\"]?\w")

# Une redirection vers un fichier. Restent permis : les descripteurs (2>&1), les puits
# (/dev/null, $null, NUL) et les dossiers temporaires, où le shell sert à exécuter.
REDIRECTION = re.compile(r"(?<![<>=\-])(?:\d|&)?>{1,2}(?![>&=])\s*(\"[^\"]*\"|'[^']*'|[^\s;|&)]+)")
CIBLES_PERMISES = re.compile(r"^['\"]?(/dev/null|\$null|nul)['\"]?$", re.IGNORECASE)
CHAINE_ENTRE_GUILLEMETS = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'")
DOSSIER_TEMPORAIRE = re.compile(r"(scratchpad|[\\/]te?mp[\\/]|appdata[\\/]local[\\/]temp)", re.IGNORECASE)

ECRITURE_POWERSHELL = re.compile(r"\b(Set-Content|Add-Content|Out-File|New-Item\b[^|;]*-Force)\b", re.IGNORECASE)

OUTILS_FICHIER = {"Read", "Edit", "Write", "NotebookEdit", "Grep", "Glob"}

REFUS_ENV = (
    ".env et .env.local appartiennent à l'utilisateur (CLAUDE.md, « Secrets ») : ni lecture ni "
    "écriture. Une nouvelle variable se documente dans .env.example."
)
REFUS_EDITION_SHELL = (
    "Édition de fichier au shell refusée (CLAUDE.md, « Outils ») : {motif}. Utiliser Edit/Write — "
    "core.autocrlf=true, un sed -i a déjà réécrit le dépôt en LF. Le shell sert à exécuter."
)


def motif_de_refus(outil: str, entree: dict) -> str | None:
    """Rend la raison du refus, ou None si l'appel est permis."""
    if outil in OUTILS_FICHIER:
        # Le motif d'une recherche n'est pas un chemin : chercher « .env » dans le code est permis.
        chemins = [entree.get(cle) or "" for cle in ("file_path", "notebook_path", "path")]
        if any(ENV_PRIVE.search(c.replace("\\", "/")) for c in chemins):
            return REFUS_ENV
        return None

    if outil not in {"Bash", "PowerShell"}:
        return None
    commande = entree.get("command") or ""
    if ENV_PRIVE.search(commande):
        return REFUS_ENV
    if SED_EN_PLACE.search(commande):
        return REFUS_EDITION_SHELL.format(motif="sed -i")
    if HEREDOC.search(commande):
        return REFUS_EDITION_SHELL.format(motif="heredoc")
    if outil == "PowerShell" and (m := ECRITURE_POWERSHELL.search(commande)):
        return REFUS_EDITION_SHELL.format(motif=m.group(1))
    # Un chevron entre guillemets n'est pas une redirection : une adresse `<x@y>` dans un
    # message de commit passait pour une écriture de fichier.
    for m in REDIRECTION.finditer(CHAINE_ENTRE_GUILLEMETS.sub('""', commande)):
        cible = m.group(1)
        if CIBLES_PERMISES.match(cible) or DOSSIER_TEMPORAIRE.search(cible):
            continue
        return REFUS_EDITION_SHELL.format(motif=f"redirection vers {cible}")
    return None


def racine_du_projet(depart: Path) -> Path | None:
    """Remonte jusqu'au dossier qui porte `tests/` et `rssresume/`.

    Partir du fichier touché, et non du projet de la session, fait tourner la suite du bon
    arbre quand le travail se fait dans un worktree.
    """
    for dossier in [depart, *depart.parents]:
        if (dossier / "tests").is_dir() and (dossier / "rssresume").is_dir():
            return dossier
    return None


def lancer_la_suite(racine: Path) -> tuple[bool, str]:
    """Lance la suite unittest de `racine`, avec l'interpréteur du hook (celui du .venv)."""
    resultat = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test*.py"],
        cwd=racine,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return resultat.returncode == 0, resultat.stderr + resultat.stdout


def queue(texte: str, lignes: int = 40) -> str:
    return "\n".join(texte.strip().splitlines()[-lignes:])


def python_modifie(racine: Path) -> bool:
    """Vrai si l'arbre de travail a des .py modifiés ou nouveaux par rapport à HEAD."""
    resultat = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=racine,
        capture_output=True,
        text=True,
    )
    return any(ligne.rstrip().endswith(".py") for ligne in resultat.stdout.splitlines())


def pre(evenement: dict) -> int:
    motif = motif_de_refus(evenement.get("tool_name", ""), evenement.get("tool_input") or {})
    if motif:
        print(motif, file=sys.stderr)
        return 2
    return 0


def post(evenement: dict) -> int:
    chemin = (evenement.get("tool_input") or {}).get("file_path") or ""
    if not chemin.endswith(".py"):
        return 0
    racine = racine_du_projet(Path(chemin).resolve().parent)
    if racine is None:
        return 0
    vert, sortie = lancer_la_suite(racine)
    if vert:
        return 0
    print(f"La suite est rouge après cette modification :\n{queue(sortie)}", file=sys.stderr)
    return 2


def stop(evenement: dict) -> int:
    # Déjà relancé une fois par ce hook : laisser rendre la main plutôt que boucler.
    if evenement.get("stop_hook_active"):
        return 0
    racine = racine_du_projet(Path(evenement.get("cwd") or os.getcwd()).resolve())
    if racine is None or not python_modifie(racine):
        return 0
    vert, sortie = lancer_la_suite(racine)
    if vert:
        return 0
    print(
        "Tâche non terminée : la suite est rouge (CLAUDE.md, « Tests »).\n" + queue(sortie),
        file=sys.stderr,
    )
    return 2


def main(argv: list[str]) -> int:
    # Claude Code lit stderr en UTF-8 ; sous Windows, Python écrirait en cp1252.
    sys.stderr.reconfigure(encoding="utf-8")
    point = argv[1] if len(argv) == 2 else ""
    if point not in {"pre", "post", "stop"}:
        print("usage : garde.py {pre|post|stop}", file=sys.stderr)
        return 1
    try:
        evenement = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if point == "pre":
        return pre(evenement)
    if point == "post":
        return post(evenement)
    return stop(evenement)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
