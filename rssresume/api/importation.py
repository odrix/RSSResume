"""La migration d'un dossier de profils JSON, ou d'un document unique, vers la base.

Elle se rejoue sans danger : un profil déjà en base n'est jamais réécrit. Le site a pu le
modifier depuis, et les fichiers ne sont plus, après la migration, qu'une sauvegarde
figée ; les réimporter écraserait ce que la personne vient d'éditer. Les fichiers
source, eux, ne sont jamais touchés, ni renommés, ni complétés de leur identifiant.

L'identifiant du document est conservé : c'est lui qui nomme le répertoire de sortie, et
le changer couperait la personne de ses journées passées. Un document sans identifiant en
reçoit un neuf.
"""

from __future__ import annotations

import json
import pathlib

from rssresume.annuaire_sqlite import AnnuaireSqlite
from rssresume.profil import CLE_ID, CLE_PROFIL, EXTENSION_PROFIL, username_valide
from rssresume.tools import console


class Bilan:
    """Ce que l'import a fait, fichier par fichier, pour le dire et pour le code de sortie."""

    def __init__(self):
        self.importes: list[str] = []
        self.deja_la: list[str] = []
        self.erreurs: list[str] = []

    @property
    def en_echec(self) -> bool:
        return bool(self.erreurs)


class Importateur:
    """Verse des documents de profil dans une base, sans jamais réécrire l'existant."""

    def __init__(self, annuaire: AnnuaireSqlite):
        self._annuaire = annuaire

    def importer(self, chemin: pathlib.Path) -> Bilan:
        """Importe un dossier (chaque `{username}.json`) ou un fichier unique.

        Un fichier fautif ou mal nommé est compté en erreur et les suivants sont importés :
        une migration qui s'arrête au premier défaut laisse une base à moitié remplie,
        sans qu'on sache où reprendre.
        """
        chemin = pathlib.Path(chemin)
        bilan = Bilan()
        if chemin.is_dir():
            fichiers = sorted(f for f in chemin.iterdir() if f.is_file() and f.suffix == EXTENSION_PROFIL)
        elif chemin.is_file():
            fichiers = [chemin]
        else:
            bilan.erreurs.append(f"{chemin} : ni dossier ni fichier.")
            fichiers = []
        for fichier in fichiers:
            self._importer_fichier(fichier, bilan)
        return bilan

    def _importer_fichier(self, fichier: pathlib.Path, bilan: Bilan) -> None:
        username = fichier.stem
        if not username_valide(username):
            bilan.erreurs.append(f"{fichier.name} : « {username} » n'est pas un nom de profil valide.")
            return
        try:
            document = _lire(fichier)
        except ValueError as exc:
            bilan.erreurs.append(str(exc))
            return

        id = document.get(CLE_ID)
        if id is not None:
            existante = self._annuaire.fiche_par_id(id) if isinstance(id, str) else None
            if existante is not None:
                if existante.username == username:
                    bilan.deja_la.append(username)
                else:
                    bilan.erreurs.append(
                        f"{fichier.name} : l'identifiant {id} est déjà celui de « {existante.username} »."
                    )
                return
        if username in self._annuaire.usernames():
            # Sans identifiant dans le fichier, le nom est la seule façon de se reconnaître :
            # celui qu'un import précédent a généré est en base, pas dans le fichier.
            if id is None:
                bilan.deja_la.append(username)
            else:
                bilan.erreurs.append(
                    f"{fichier.name} : « {username} » est déjà en base sous un autre identifiant."
                )
            return
        try:
            fiche = self._annuaire.creer(username, document, id=id)
        except ValueError as exc:  # document fautif, ou `ProfilDejaPris` d'un import concurrent
            bilan.erreurs.append(f"{fichier.name} : {exc}")
            return
        # L'identifiant est dit : généré, il n'est écrit nulle part ailleurs qu'en base, et
        # c'est sous lui que les journées passées de la personne doivent être rangées.
        console.log(f"Import : {username} → {fiche.id}")
        bilan.importes.append(username)


def _lire(fichier: pathlib.Path) -> dict:
    """Le document d'un fichier, sous la même règle que `profil._document` : un objet JSON
    s'il commence par une accolade, le texte du profil sinon."""
    try:
        contenu = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"{fichier.name} : illisible ({exc}).") from exc
    if not contenu:
        raise ValueError(f"{fichier.name} : vide.")
    if not contenu.startswith("{"):
        return {CLE_PROFIL: contenu}
    try:
        document = json.loads(contenu)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{fichier.name} : JSON invalide ({exc}).") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{fichier.name} : un profil est un objet JSON.")
    return document


def rendre_compte(bilan: Bilan) -> None:
    """Le bilan dans la console : ce qui est entré, ce qui y était, ce qui a été refusé."""
    console.log(f"Import : {len(bilan.importes)} importé(s) : {', '.join(bilan.importes) or '-'}")
    console.log(f"Import : {len(bilan.deja_la)} déjà en base : {', '.join(bilan.deja_la) or '-'}")
    for erreur in bilan.erreurs:
        console.error(f"Import : {erreur}")
