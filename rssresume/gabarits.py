"""Les profils pré-remplis proposés pour chaque métier.

Un gabarit est une donnée hors du code : il pré-remplit une saisie, sans créer un lien
avec le document ensuite enregistré ni figer une modification personnelle. Sa forme passe
par la même validation que les profils afin que l'API ne propose jamais un document inutilisable.
"""

from __future__ import annotations

import json
import pathlib
import re

from rssresume.categories import Catalogue
from rssresume.profil import profil_depuis_dict

CHEMIN_BUILTIN = pathlib.Path(__file__).with_name("gabarits.json")
MOTIF_METIER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


class Gabarit:
    """Un document de départ, sans identité ni lien avec un compte."""

    def __init__(self, metier: str, libelle: str, document: dict):
        self.metier = metier
        self.libelle = libelle
        self.document = document

    def en_json(self) -> dict:
        return {
            "metier": self.metier,
            "libelle": self.libelle,
            **self.document,
        }


class Gabarits:
    """La liste validée des gabarits disponibles."""

    def __init__(self, gabarits: list[Gabarit]):
        self._gabarits = tuple(gabarits)

    def __iter__(self):
        return iter(self._gabarits)

    def __len__(self) -> int:
        return len(self._gabarits)

    @classmethod
    def depuis_fichier(cls, chemin: pathlib.Path, catalogue: Catalogue | None = None) -> "Gabarits":
        """Charge et valide tout le fichier avant que l'API puisse l'exposer.

        Le catalogue est obligatoire au démarrage de l'installation réelle : il vérifie
        l'existence et la visibilité publiques. Les utilisateurs unitaires peuvent charger
        la donnée seule pour tester sa forme sans devoir importer un catalogue fictif.
        """
        chemin = pathlib.Path(chemin)
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Gabarits {chemin} : illisible ({exc}).") from exc
        try:
            document = json.loads(contenu)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gabarits {chemin} : JSON invalide ({exc}).") from exc
        return cls.depuis_document(document, str(chemin), catalogue)

    @classmethod
    def depuis_document(cls, document: object, origine: str, catalogue: Catalogue | None = None) -> "Gabarits":
        if not isinstance(document, dict) or not document:
            raise ValueError(f"{origine} : une liste non vide de gabarits est attendue.")

        gabarits = []
        for metier, brut in sorted(document.items(), key=lambda item: item[0]):
            if not isinstance(metier, str) or not MOTIF_METIER.match(metier):
                raise ValueError(f"{origine} : identifiant de métier invalide « {metier} ».")
            if not isinstance(brut, dict):
                raise ValueError(f"{origine} : gabarit « {metier} » doit être un objet JSON.")
            libelle = brut.get("libelle")
            if not isinstance(libelle, str) or not libelle.strip():
                raise ValueError(f"{origine} : gabarit « {metier} » sans libellé.")

            document_profil = {
                cle: brut[cle]
                for cle in ("profil", "stack", "email", "prenom", "securite", "axes", "categories")
                if cle in brut
            }
            profil_depuis_dict(document_profil, f"{origine}, gabarit « {metier} »", catalogue, "")

            categories = document_profil.get("categories")
            if not isinstance(categories, list) or not categories:
                raise ValueError(f"{origine} : gabarit « {metier} » sans catégories par défaut.")
            if catalogue is not None:
                for categorie in categories:
                    entree = catalogue.entree(categorie)
                    if entree is None or not entree.publique:
                        raise ValueError(
                            f"{origine} : gabarit « {metier} », catégorie « {categorie} » "
                            "doit exister et être publique."
                        )

            gabarits.append(Gabarit(metier, libelle.strip(), document_profil))
        return cls(gabarits)


BUILTIN_GABARITS = Gabarits
