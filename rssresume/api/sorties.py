"""Les journées produites pour un profil, et leurs audios, lus sur le disque.

Le seul endroit où l'API touche au système de fichiers. Tout ce qui y entre vient d'une
URL — un identifiant, une date, un nom de fichier — et une URL se fabrique : chaque
segment est donc validé contre un motif strict, puis le fichier doit figurer dans la
liste de sa journée, puis son chemin résolu doit rester sous le dossier du profil. Trois
barrières indépendantes, pour qu'une seule défaillance ne suffise pas à sortir du volume.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

from rssresume import newsletter, runlog
from rssresume.liens import lien_sur
from rssresume.models import Link
from rssresume.newsletter import Lettre

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


class ContenuJournee:
    """Ce qu'une journée raconte : la lettre que l'email a portée, et les audios du disque.

    La lettre et non les journaux bruts : c'est elle qui décide de ce qu'un lecteur voit —
    quels articles sont « à lire », lesquels « à surveiller », quelle durée s'annonce.
    Relire les journaux une seconde fois, ailleurs, finirait par ne plus dire comme l'email.
    """

    def __init__(self, date: dt.date, lettre: Lettre, audios: list[Audio], en_cours: bool = False):
        self.date = date
        self.lettre = lettre
        self.audios = audios
        #: Vrai quand la tournée écrit encore la journée : ses journaux manquent ou sont
        #: tronqués. Distinct d'une journée sans article, qui est finie et vide.
        self.en_cours = en_cours

    @property
    def raison(self) -> str | None:
        """La phrase d'une journée sans article, la même que l'email ; `None` sinon."""
        if self.en_cours or self.lettre.sections:
            return None
        return f"Aucun article trouvé pour le {newsletter.date_longue(self.date)}."

    def en_json(self) -> dict:
        """Les textes partent bruts : les échapper est le travail du rendu, qui seul sait
        dans quel contexte ils tombent. Les URL, elles, sont filtrées ici."""
        lettre = self.lettre
        return {
            "date": self.date.isoformat(),
            "audios": [audio.en_json() for audio in self.audios],
            "ecoute": newsletter.duree(lettre.total_secondes),
            "racontees": lettre.racontees,
            "montage": None
            if lettre.montage is None
            else {
                "audio": lettre.montage_path.name if lettre.montage_path else None,
                "ecoute": lettre.montage_ecoute,
            },
            "raison": self.raison,
            "en_cours": self.en_cours,
            "categories": [
                {
                    "categorie": section.category,
                    "racontee": section.racontee,
                    "resume": section.summary_text,
                    "audio": section.audio_name,
                    "ecoute": section.ecoute,
                    "articles": [_lien_json(lien) for lien in section.links],
                    "a_surveiller": [_lien_json(lien) for lien in section.watchlist],
                }
                for section in lettre.sections
            ],
        }


def _lien_json(lien: Link) -> dict:
    return {"titre": lien.title, "source": lien.source, "url": lien_sur(lien.url)}


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

    def contenu(self, id: str, texte_date: str) -> ContenuJournee | None:
        """Le contenu d'une journée produite, relu de ses journaux ; sinon `None`.

        La lecture est exactement celle de `--send-only` — `read_day`, `read_montage`,
        `Lettre.compose` — pour que le site montre ce que l'email a montré, sans un appel
        IA ni une seconde façon de relire un journal.
        """
        date = date_valide(texte_date)
        if date is None:
            return None
        jour = self.dossier(id) / date.isoformat()
        if not jour.is_dir() or jour.is_symlink():
            return None
        if not jour.resolve().is_relative_to(self.dossier(id).resolve()):
            return None
        audios = self._audios(jour)
        if not any(jour.glob(f"*{runlog.LOG_SUFFIX}")) and not any(
            jour.glob(f"*{runlog.NO_ARTICLE_SUFFIX}")
        ):
            # Le répertoire est créé avant le premier journal : vide, la journée n'est pas
            # « sans article », elle n'est pas encore écrite.
            return ContenuJournee(date, Lettre.compose(date, []), audios, en_cours=True)
        try:
            digests = runlog.read_day(jour)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # Un journal s'écrit en place : lu pendant que la tournée l'écrit, il est
            # tronqué. Ce n'est pas une panne, c'est une journée pas encore finie.
            return ContenuJournee(date, Lettre.compose(date, []), audios, en_cours=True)
        lettre = Lettre.compose(date, digests, montage=runlog.read_montage(jour))
        return ContenuJournee(date, lettre, audios)

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

    def couts(self, id: str, aujourd_hui: dt.date) -> dict:
        """Les coûts de sept et trente jours, relus des sorties du profil.

        Les journaux restent la source de vérité : aucun appel fournisseur n'est rejoué
        pour présenter l'administration, et chaque intervalle signe les modèles absents.
        """
        dossier = self.dossier(id)
        couts_7 = runlog.couts_periode(dossier, aujourd_hui - dt.timedelta(days=6), aujourd_hui)
        couts_30 = runlog.couts_periode(dossier, aujourd_hui - dt.timedelta(days=29), aujourd_hui)
        return {"couts_7j": couts_7, "couts_30j": couts_30}

    @staticmethod
    def _audios(jour: pathlib.Path) -> list[Audio]:
        """Les fichiers audio d'une journée. Les liens symboliques n'en sont pas : ils
        pourraient pointer hors du volume."""
        return [
            Audio(fichier)
            for fichier in sorted(jour.iterdir(), key=lambda f: f.name)
            if fichier.suffix in TYPES_AUDIO and fichier.is_file() and not fichier.is_symlink()
        ]
