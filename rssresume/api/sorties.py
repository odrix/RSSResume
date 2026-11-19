"""Les journées produites pour un profil, et leurs audios, lus sur le disque.

Le seul endroit où l'API touche au système de fichiers. Tout ce qui y entre vient d'une
URL — un identifiant, une date, un nom de fichier — et une URL se fabrique : chaque
segment est donc validé contre un motif strict, puis le fichier doit figurer dans la
liste de sa journée, puis son chemin résolu doit rester sous le dossier du profil. Trois
barrières indépendantes, pour qu'une seule défaillance ne suffise pas à sortir du volume.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

#: Le nom d'un répertoire de journée, tel que `digest.py` l'écrit.
MOTIF_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Les formats que la synthèse vocale produit : mp3 chez les fournisseurs, wav avec espeak.
TYPES_AUDIO = {".mp3": "audio/mpeg", ".wav": "audio/wav"}


class Audio:
    """Un fichier audio d'une journée."""

    def __init__(self, chemin: pathlib.Path):
        self.chemin = chemin
        self.nom = chemin.name
        self.taille = chemin.stat().st_size

    @property
    def type_mime(self) -> str:
        return TYPES_AUDIO[self.chemin.suffix]

    def en_json(self) -> dict:
        return {"nom": self.nom, "taille": self.taille}


class Journee:
    """Une journée produite : sa date et ses audios, triés par nom."""

    def __init__(self, date: dt.date, audios: list[Audio]):
        self.date = date
        self.audios = audios

    def en_json(self) -> dict:
        return {"date": self.date.isoformat(), "audios": [audio.en_json() for audio in self.audios]}


def date_valide(texte: str) -> dt.date | None:
    """La date d'un segment d'URL ou d'un nom de répertoire, ou `None`.

    Le motif d'abord : `fromisoformat` accepte depuis Python 3.11 des formes compactes
    (`20260823`) qui ne nomment aucun répertoire de sortie.
    """
    if not MOTIF_DATE.match(texte):
        return None
    try:
        return dt.date.fromisoformat(texte)
    except ValueError:
        return None


def nom_valide(nom: str) -> bool:
    """Vrai pour un nom de fichier nu, sans séparateur ni remontée."""
    return bool(nom) and "/" not in nom and "\\" not in nom and ".." not in nom and "\0" not in nom


class Sorties:
    """La racine des sorties, `{RSSRESUME_OUTPUT_DIR}`, vue profil par profil.

    Un profil y écrit sous `{id}/` et non sous son nom : le nom se change sur le site, un
    identifiant jamais, et les journées passées suivent la personne.
    """

    def __init__(self, racine: pathlib.Path):
        self.racine = pathlib.Path(racine)

    def dossier(self, id: str) -> pathlib.Path:
        return self.racine / id

    def journees(self, id: str) -> list[Journee]:
        """Les journées du profil, la plus récente d'abord. Aucune encore : liste vide."""
        dossier = self.dossier(id)
        if not dossier.is_dir():
            return []
        journees = []
        for entree in dossier.iterdir():
            date = date_valide(entree.name)
            if date is not None and entree.is_dir() and not entree.is_symlink():
                journees.append(Journee(date, self._audios(entree)))
        return sorted(journees, key=lambda journee: journee.date, reverse=True)

    def audio(self, id: str, texte_date: str, nom: str) -> Audio | None:
        """L'audio demandé, s'il existe et reste sous le dossier du profil ; sinon `None`."""
        date = date_valide(texte_date)
        if date is None or not nom_valide(nom):
            return None
        jour = self.dossier(id) / date.isoformat()
        if not jour.is_dir():
            return None
        audio = next((audio for audio in self._audios(jour) if audio.nom == nom), None)
        if audio is None:
            return None
        if not audio.chemin.resolve().is_relative_to(self.dossier(id).resolve()):
            return None
        return audio

    @staticmethod
    def _audios(jour: pathlib.Path) -> list[Audio]:
        """Les fichiers audio d'une journée. Les liens symboliques n'en sont pas : ils
        pourraient pointer hors du volume."""
        return [
            Audio(fichier)
            for fichier in sorted(jour.iterdir(), key=lambda f: f.name)
            if fichier.suffix in TYPES_AUDIO and fichier.is_file() and not fichier.is_symlink()
        ]
