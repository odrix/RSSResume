"""Les profils en base SQLite : la source qu'éditent le site et l'API.

Le dossier de `{username}.json` suffisait tant qu'une personne éditait ses fichiers à la
main. Dès qu'un site les écrit pendant que la tournée les lit, il faut ce qu'un dossier ne
donne pas : une écriture qui se voit entière ou pas du tout, un nom qui ne peut pas être
pris deux fois, et une date de modification qu'on n'a pas à déduire du disque.

SQLite et non un serveur de base : le projet tourne sur la bibliothèque standard, et la
base vit dans le même volume que la sortie. Deux processus y accèdent — le travailleur
quotidien qui lit, l'API qui écrit — d'où le mode WAL : un lecteur n'y bloque jamais un
écrivain, ni l'inverse.

Le document stocké est celui que `profil_depuis_dict` accepte, `id` compris : il est validé
à l'écriture, pour que l'API refuse ce que la tournée refuserait, et de nouveau à la
lecture, parce qu'une base se modifie aussi à la main.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib
import sqlite3
from typing import Iterator

from rssresume.axes import CLE_AXES
from rssresume.categories import Catalogue, CatalogueOuvert
from rssresume.certfr.stack import CLE_STACK
from rssresume.profil import (
    CLE_CATEGORIES,
    CLE_EMAIL,
    CLE_FLUX_EXCLUS,
    CLE_ID,
    CLE_PRENOM,
    CLE_PROFIL,
    CLE_SECURITE,
    SECURITE_PAR_DEFAUT,
    Annuaire,
    Profil,
    id_valide,
    nouvel_id,
    profil_depuis_dict,
    valider_username,
)

#: Attente maximale d'un verrou d'écriture, en millisecondes. Une écriture de l'API dure
#: quelques millisecondes ; cinq secondes couvrent une rafale sans laisser une requête
#: pendre indéfiniment.
ATTENTE_VERROU_MS = 5000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profils (
    id         TEXT PRIMARY KEY NOT NULL,
    username   TEXT NOT NULL UNIQUE,
    document   TEXT NOT NULL,
    cree_le    TEXT NOT NULL,
    modifie_le TEXT NOT NULL
)
"""

#: Le catalogue des catégories, une ligne par libellé FreshRSS. Le document est l'entrée
#: sous sa forme d'échange (`CategorieCatalogue.en_document`), comme `profils.document` :
#: une seule validation, `Catalogue.depuis_document`, pour le fichier et pour la base.
_SCHEMA_CATEGORIES = """
CREATE TABLE IF NOT EXISTS categories (
    libelle  TEXT PRIMARY KEY NOT NULL,
    document TEXT NOT NULL
)
"""


def _maintenant() -> str:
    """L'horodatage des écritures, en UTC : la base est partagée, le fuseau ne l'est pas."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class ProfilInconnu(ValueError):
    """Le nom ne désigne aucun profil de la base.

    `ValueError` pour que la tournée et `--profil` le traitent comme un nom inconnu du
    dossier ; une classe à part pour que l'API en fasse un 404 et non un 422.
    """


class ProfilDejaPris(ValueError):
    """Le nom ou l'identifiant est déjà celui d'un autre profil."""


class Fiche:
    """Un profil de la base : le document, et ce que la base sait de lui.

    Le document est gardé sous sa forme normalisée — les cinq clés du format, rien
    d'autre — pour que ce que l'API rend soit exactement ce que la tournée lit.
    """

    def __init__(
        self, id: str, username: str, document: dict, cree_le: str, modifie_le: str
    ):
        self.id = id
        self.username = username
        self.document = document
        self.cree_le = cree_le
        self.modifie_le = modifie_le

    @property
    def profil(self) -> Profil:
        """Le profil validé. Un document modifié à la main et devenu fautif : `ValueError`."""
        return profil_depuis_dict(self.document, self.username)

    def resume_json(self) -> dict:
        """Ce qu'une liste de profils montre : de quoi reconnaître une personne."""
        return {
            "id": self.id,
            "username": self.username,
            "prenom": self.document.get(CLE_PRENOM, ""),
            "email": list(self.document.get(CLE_EMAIL, [])),
            "modifie_le": self.modifie_le,
        }

    def complet_json(self) -> dict:
        """Le profil entier, tel que le site l'édite."""
        corps = {
            "id": self.id,
            "username": self.username,
            "profil": self.document.get(CLE_PROFIL, ""),
            "stack": list(self.document.get(CLE_STACK, [])),
            "email": list(self.document.get(CLE_EMAIL, [])),
            "prenom": self.document.get(CLE_PRENOM, ""),
            # Un document écrit avant la clé ne la porte pas : il est servi au défaut, et
            # c'est le défaut que le site doit montrer.
            "securite": self.document.get(CLE_SECURITE, SECURITE_PAR_DEFAUT.value),
            "modifie_le": self.modifie_le,
        }
        if CLE_AXES in self.document:
            corps[CLE_AXES] = list(self.document[CLE_AXES])
        if CLE_CATEGORIES in self.document:
            corps[CLE_CATEGORIES] = list(self.document[CLE_CATEGORIES])
        if CLE_FLUX_EXCLUS in self.document:
            corps[CLE_FLUX_EXCLUS] = list(self.document[CLE_FLUX_EXCLUS])
        return corps


def document_normalise(
    saisie: object,
    id: str,
    origine: str,
    catalogue: "Catalogue | None" = None,
) -> dict:
    """Le document à écrire, validé : `ValueError` avec le message de `profil_depuis_dict`.

    Seules les clés du format sont gardées : une clé de plus ne serait lue par personne,
    et un document qui ne se relit pas tel qu'on l'a écrit trompe celui qui l'édite. Les
    adresses sont rangées en liste et le texte rogné — ce que la lecture ferait de toute
    façon —, pour que le site relise ce que la tournée servira.
    """
    if not isinstance(saisie, dict):
        raise ValueError(f"{origine} : un profil est un objet JSON, pas {type(saisie).__name__}.")
    brut = {
        cle: saisie[cle]
        for cle in (
            CLE_PROFIL, CLE_STACK, CLE_EMAIL, CLE_PRENOM, CLE_SECURITE, CLE_AXES, CLE_CATEGORIES,
            CLE_FLUX_EXCLUS,
        )
        if cle in saisie
    }
    # Un formulaire vidé envoie une liste vide là où un fichier omettait la clé : c'est
    # le même « aucun destinataire », et le document écrit omet la clé comme le fichier.
    if brut.get(CLE_EMAIL) == []:
        del brut[CLE_EMAIL]
    # Une saisie vide signifie « revenir aux axes historiques », comme email vide
    # signifie retirer les destinataires : on omet la clé plutôt que d'inventer une liste.
    if brut.get(CLE_AXES) == []:
        del brut[CLE_AXES]
    if brut.get(CLE_CATEGORIES) == []:
        del brut[CLE_CATEGORIES]
    # N'exclure aucun flux est l'état ordinaire : le document l'écrit en omettant la clé.
    if brut.get(CLE_FLUX_EXCLUS) == []:
        del brut[CLE_FLUX_EXCLUS]
    brut[CLE_ID] = id
    profil = profil_depuis_dict(brut, origine, catalogue, origine)
    if not id_valide(profil.id):
        raise ValueError(f"{origine} : identifiant de profil invalide (« {id} »).")
    document = {CLE_ID: id, CLE_PROFIL: profil.texte, CLE_STACK: list(brut.get(CLE_STACK) or [])}
    if profil.emails:
        document[CLE_EMAIL] = list(profil.emails)
    document[CLE_PRENOM] = profil.prenom
    document[CLE_SECURITE] = profil.securite.value
    if profil.axes.sont_declares:
        document[CLE_AXES] = profil.axes.en_document()
    if profil.categories is not None:
        document[CLE_CATEGORIES] = list(profil.categories)
    if profil.flux_exclus:
        document[CLE_FLUX_EXCLUS] = profil.flux_exclus.en_document()
    return document


class AnnuaireSqlite(Annuaire):
    """Les profils d'une base SQLite, une ligne par personne.

    Une connexion par opération, fermée aussitôt : l'API sert chaque requête dans son
    propre fil, et une connexion SQLite ne se partage pas entre fils. L'ouverture coûte
    moins qu'une requête HTTP, et rien ne reste verrouillé entre deux.

    Relue à chaque appel, comme le dossier : ce que le site écrit à 3 h 59 est servi à 4 h.
    """

    def __init__(self, chemin: pathlib.Path):
        self.chemin = pathlib.Path(chemin)
        with self._connexion():
            pass

    @contextlib.contextmanager
    def _connexion(self) -> Iterator[sqlite3.Connection]:
        """Une connexion en autocommit, WAL posé, schéma garanti.

        Autocommit pour que chaque écriture ouvre elle-même sa transaction, en
        `BEGIN IMMEDIATE` : le verrou d'écriture est pris d'emblée, et deux écrivains
        concurrents attendent leur tour au lieu de se découvrir en conflit au commit.
        """
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        connexion = sqlite3.connect(
            self.chemin, timeout=ATTENTE_VERROU_MS / 1000, isolation_level=None
        )
        try:
            connexion.execute(f"PRAGMA busy_timeout = {ATTENTE_VERROU_MS}")
            connexion.execute("PRAGMA journal_mode = WAL")
            connexion.execute(_SCHEMA)
            connexion.execute(_SCHEMA_CATEGORIES)
            yield connexion
        finally:
            connexion.close()

    @contextlib.contextmanager
    def _ecriture(self) -> Iterator[sqlite3.Connection]:
        """Une transaction d'écriture : tout est écrit, ou rien."""
        with self._connexion() as connexion:
            connexion.execute("BEGIN IMMEDIATE")
            try:
                yield connexion
            except BaseException:
                connexion.execute("ROLLBACK")
                raise
            connexion.execute("COMMIT")

    # --- Ce que la tournée lit ------------------------------------------------------

    def usernames(self) -> list[str]:
        with self._connexion() as connexion:
            lignes = connexion.execute("SELECT username FROM profils ORDER BY username").fetchall()
        return [username for (username,) in lignes]

    def profil(self, username: str) -> Profil:
        return self.fiche(username).profil

    # --- Ce que l'API lit et écrit ----------------------------------------------------

    def fiches(self) -> list[Fiche]:
        """Toutes les fiches, triées par nom.

        Les documents n'y sont pas revalidés : un profil devenu fautif doit rester
        visible dans la liste, c'est là qu'on viendra le corriger.
        """
        with self._connexion() as connexion:
            lignes = connexion.execute(
                "SELECT id, username, document, cree_le, modifie_le FROM profils ORDER BY username"
            ).fetchall()
        return [self._fiche(ligne) for ligne in lignes]

    def fiche(self, username: str) -> Fiche:
        """La fiche de `username`. Absente : `ProfilInconnu`."""
        with self._connexion() as connexion:
            ligne = connexion.execute(
                "SELECT id, username, document, cree_le, modifie_le FROM profils WHERE username = ?",
                (username,),
            ).fetchone()
        if ligne is None:
            raise ProfilInconnu(f"Profil inconnu : « {username} ».")
        return self._fiche(ligne)

    def fiche_par_id(self, id: str) -> Fiche | None:
        """La fiche d'identifiant `id`, ou `None` : l'import s'en sert pour se reconnaître."""
        with self._connexion() as connexion:
            ligne = connexion.execute(
                "SELECT id, username, document, cree_le, modifie_le FROM profils WHERE id = ?",
                (id,),
            ).fetchone()
        return None if ligne is None else self._fiche(ligne)

    def creer(self, username: str, saisie: object, id: str | None = None) -> Fiche:
        """Écrit un nouveau profil. Nom invalide ou document fautif : `ValueError`.

        Nom ou identifiant déjà pris : `ProfilDejaPris`. C'est la contrainte d'unicité qui
        tranche, et non une lecture préalable : deux créations simultanées du même nom ne
        peuvent pas passer toutes les deux.
        """
        username = valider_username(username)
        id = id or nouvel_id()
        document = document_normalise(saisie, id, username, self.catalogue())
        horodatage = _maintenant()
        try:
            with self._ecriture() as connexion:
                connexion.execute(
                    "INSERT INTO profils (id, username, document, cree_le, modifie_le) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (id, username, _json(document), horodatage, horodatage),
                )
        except sqlite3.IntegrityError as exc:
            raise ProfilDejaPris(f"Le profil « {username} » existe déjà.") from exc
        return Fiche(id, username, document, horodatage, horodatage)

    def modifier(self, username: str, saisie: object) -> Fiche:
        """Remplace le document de `username`, son id et son nom gardés. Absent : `ProfilInconnu`."""
        with self._ecriture() as connexion:
            ligne = connexion.execute(
                "SELECT id, cree_le FROM profils WHERE username = ?", (username,)
            ).fetchone()
            if ligne is None:
                raise ProfilInconnu(f"Profil inconnu : « {username} ».")
            id, cree_le = ligne
            document = document_normalise(saisie, id, username)
            horodatage = _maintenant()
            connexion.execute(
                "UPDATE profils SET document = ?, modifie_le = ? WHERE id = ?",
                (_json(document), horodatage, id),
            )
        return Fiche(id, username, document, cree_le, horodatage)

    def supprimer(self, username: str) -> None:
        """Retire le profil de la base — et de la tournée. Ses sorties restent sur le disque."""
        with self._ecriture() as connexion:
            supprimees = connexion.execute(
                "DELETE FROM profils WHERE username = ?", (username,)
            ).rowcount
        if not supprimees:
            raise ProfilInconnu(f"Profil inconnu : « {username} ».")

    # --- Le catalogue des catégories -------------------------------------------------

    def catalogue(self) -> Catalogue:
        """Le catalogue en base, revalidé à chaque lecture. Table vide : `CatalogueOuvert`.

        Revalidé pour la même raison que les profils : une base se modifie aussi à la
        main, et une ligne devenue fautive doit faire échouer la tournée au lancement
        plutôt que de servir une catégorie privée à qui n'en est pas propriétaire.
        """
        with self._connexion() as connexion:
            lignes = connexion.execute(
                "SELECT libelle, document FROM categories ORDER BY libelle"
            ).fetchall()
        if not lignes:
            return CatalogueOuvert()
        document = {}
        for libelle, contenu in lignes:
            try:
                document[libelle] = json.loads(contenu)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Catalogue {self.chemin}, « {libelle} » : document JSON illisible en base ({exc})."
                ) from exc
        return Catalogue.depuis_document(document, str(self.chemin))

    def remede_sans_catalogue(self) -> str:
        return (
            "Importer le catalogue dans la base (python -m rssresume.api importer-catalogue "
            "<fichier.json>, voir docs/categories.exemple.json)."
        )

    def remplacer_catalogue(self, catalogue: Catalogue) -> None:
        """Remplace tout le catalogue, dans une transaction.

        Remplacer et non fusionner : le fichier importé est la source de vérité, et une
        catégorie qu'on en retire doit cesser d'être servie — fusionnée, une catégorie
        privée retirée resterait en base sans que personne ne s'en souvienne.
        """
        with self._ecriture() as connexion:
            connexion.execute("DELETE FROM categories")
            connexion.executemany(
                "INSERT INTO categories (libelle, document) VALUES (?, ?)",
                [(entree.libelle, _json(entree.en_document())) for entree in catalogue.entrees()],
            )

    @staticmethod
    def _fiche(ligne: tuple) -> Fiche:
        id, username, document, cree_le, modifie_le = ligne
        try:
            contenu = json.loads(document)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{username} : document JSON illisible en base ({exc}).") from exc
        if not isinstance(contenu, dict) or contenu.get(CLE_ID) != id:
            raise ValueError(f"{username} : le document en base ne porte pas l'identifiant {id}.")
        return Fiche(id, username, contenu, cree_le, modifie_le)


def _json(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True)
