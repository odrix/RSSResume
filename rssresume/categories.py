"""Le catalogue des catégories : qui reçoit quoi, parmi ce que le FreshRSS partagé contient.

Un seul FreshRSS sert plusieurs personnes, et tout ce qu'il contient n'est pas à tout le
monde : la veille concurrentielle d'une entreprise, alertes Google, « Veille marché » : ne
doit ni être notée, ni résumée, ni montrée à quelqu'un d'extérieur. Le catalogue décrit
chaque catégorie : libellé FreshRSS, description lisible, métiers concernés, et visibilité
,publique, ou privée avec ses propriétaires.

La règle par défaut est la fermeture : une catégorie absente du catalogue n'est servie à
personne. Une catégorie créée dans FreshRSS ne doit pas apparaître chez tout le monde parce
que quelqu'un l'a créée, et une faute de recopie dans un libellé doit priver la catégorie
de lecteurs, jamais la donner à tous.

Le catalogue vit dans la base des profils (`annuaire_sqlite`), pas dans le dépôt : son
contenu réel nomme la veille d'une entreprise et ses propriétaires. Il s'échange en JSON
(`docs/categories.exemple.json`), dans la forme de `llm/providers.json`, un objet dont les
clés sont les libellés, `_` en tête pour un commentaire.
"""

from __future__ import annotations

import json
import pathlib
from typing import Iterable

from rssresume.profil import valider_username
from rssresume.tools.text import casefold_ascii

VISIBILITE_PUBLIQUE = "publique"
VISIBILITE_PRIVEE = "privee"
VISIBILITES = (VISIBILITE_PUBLIQUE, VISIBILITE_PRIVEE)

CLE_DESCRIPTION = "description"
CLE_METIERS = "metiers"
CLE_VISIBILITE = "visibilite"
CLE_PROPRIETAIRES = "proprietaires"
CLES = (CLE_DESCRIPTION, CLE_METIERS, CLE_VISIBILITE, CLE_PROPRIETAIRES)

#: Préfixe des clés de commentaire, comme dans `llm/providers.json`.
PREFIXE_COMMENTAIRE = "_"


class CategorieCatalogue:
    """Une catégorie décrite : ce qu'elle est, pour qui, et qui peut la lire.

    La visibilité se déduit des propriétaires et n'est pas stockée à part : une catégorie
    privée sans propriétaire, ou publique avec, est une contradiction que la lecture refuse
,    il n'y a donc qu'une seule source pour « qui la lit ».
    """

    def __init__(
        self,
        libelle: str,
        description: str,
        metiers: Iterable[str],
        proprietaires: Iterable[str] = (),
    ):
        self.libelle = libelle
        self.description = description
        #: Liste libre pour l'instant : le vocabulaire se fixera avec les gabarits.
        self.metiers = tuple(metiers)
        self.proprietaires = tuple(proprietaires)

    @property
    def publique(self) -> bool:
        return not self.proprietaires

    def visible_par(self, username: str) -> bool:
        return self.publique or username in self.proprietaires

    def proposition_json(self) -> dict:
        """Ce que le site montre d'une catégorie à cocher : de quoi choisir, rien de plus.

        Ni les propriétaires ni les métiers : la page n'en a pas l'usage, et les
        propriétaires d'une catégorie privée nommeraient d'autres personnes à qui la lit.
        `privee` dit seulement à la personne que celle-ci n'est montrée qu'à elle.
        """
        return {"libelle": self.libelle, "description": self.description, "privee": not self.publique}

    def en_document(self) -> dict:
        """L'entrée sous sa forme d'échange, celle que `Catalogue.depuis_document` relit."""
        document = {
            CLE_DESCRIPTION: self.description,
            CLE_METIERS: list(self.metiers),
            CLE_VISIBILITE: VISIBILITE_PUBLIQUE if self.publique else VISIBILITE_PRIVEE,
        }
        if not self.publique:
            document[CLE_PROPRIETAIRES] = list(self.proprietaires)
        return document


class Catalogue:
    """Les catégories décrites, et la règle qui en découle : servie si décrite et visible.

    Les libellés se comparent repliés en casse et en accents, comme `est_deterministe` :
    un libellé recopié perd ses accents en route. Une faute plus grave rend la catégorie
    absente, donc servie à personne, l'erreur ferme, elle ne fuit pas.
    """

    def __init__(self, entrees: Iterable[CategorieCatalogue] = ()):
        self._entrees: dict[str, CategorieCatalogue] = {}
        for entree in entrees:
            cle = cle_categorie(entree.libelle)
            if cle in self._entrees:
                raise ValueError(
                    f"Catalogue : « {entree.libelle} » et « {self._entrees[cle].libelle} » "
                    "désignent la même catégorie une fois casse et accents retirés."
                )
            self._entrees[cle] = entree

    @property
    def ouvert(self) -> bool:
        """Faux : seul ce qui est décrit est servi. Voir `CatalogueOuvert`."""
        return False

    def entree(self, libelle: str) -> CategorieCatalogue | None:
        return self._entrees.get(cle_categorie(libelle))

    def entrees(self) -> list[CategorieCatalogue]:
        return list(self._entrees.values())

    def visible(self, categorie: str, username: str) -> bool:
        entree = self.entree(categorie)
        return entree is not None and entree.visible_par(username)

    def servies(self, categories: list[str], username: str) -> list[str]:
        """Les catégories que `username` reçoit, dans l'ordre reçu."""
        return [categorie for categorie in categories if self.visible(categorie, username)]

    def servie_a(self, categorie: str, usernames: Iterable[str]) -> bool:
        """Vrai si au moins une de ces personnes reçoit la catégorie."""
        return any(self.visible(categorie, username) for username in usernames)

    def hors_catalogue(self, categories: list[str]) -> list[str]:
        """Les catégories que le catalogue ne décrit pas, servies à personne."""
        return [categorie for categorie in categories if self.entree(categorie) is None]

    def proposables(self, username: str) -> list[CategorieCatalogue]:
        """Les catégories que `username` peut suivre : les publiques, et ses privées.

        Une seule règle pour la page qui les propose et pour le refus qui les cite : sans
        quoi la page pourrait offrir à cocher ce que l'enregistrement refuserait ensuite.
        """
        return [entree for entree in self.entrees() if entree.visible_par(username)]

    def abonnement(
        self,
        categories: Iterable[str],
        username: str,
        origine: str,
        acquises: Iterable[str] = (),
    ) -> tuple[str, ...]:
        """Les catégories que `username` déclare suivre, sous leur libellé du catalogue.

        Le libellé canonique et non celui saisi : le site relit ce que la tournée sert, et
        une catégorie renommée dans le catalogue se voit à la relecture.

        Une catégorie privée d'un autre reçoit **le même** refus qu'une inconnue : un
        message qui la distinguerait révélerait qu'elle existe. Les catégories proposées
        dans le message sont celles que `username` pourrait suivre, jamais davantage.

        `acquises` : celles que la personne suit déjà, gardées sous leur libellé stocké même
        si le catalogue ne les décrit plus ou ne les lui montre plus. Seul ce qu'on ajoute
        est un choix à vérifier ; ce qui était acquis, la tournée le refiltre au passage.
        """
        deja = {cle_categorie(libelle): libelle for libelle in acquises}
        libelles = []
        for categorie in categories:
            if cle_categorie(categorie) in deja:
                libelles.append(deja[cle_categorie(categorie)])
                continue
            entree = self.entree(categorie)
            if entree is None or not entree.visible_par(username):
                proposables = [e.libelle for e in self.proposables(username)]
                raise ValueError(
                    f"{origine} : catégorie « {categorie} » inconnue du catalogue. "
                    f"Catégories proposées : {', '.join(proposables) or '(aucune)'}."
                )
            libelles.append(entree.libelle)
        return tuple(libelles)

    def en_document(self) -> dict:
        return {entree.libelle: entree.en_document() for entree in self.entrees()}

    @classmethod
    def depuis_fichier(cls, chemin: pathlib.Path) -> "Catalogue":
        """Le catalogue d'un fichier JSON. Illisible ou fautif : `ValueError`."""
        chemin = pathlib.Path(chemin)
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Catalogue {chemin} : illisible ({exc}).") from exc
        try:
            document = json.loads(contenu)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Catalogue {chemin} : JSON invalide ({exc}).") from exc
        return cls.depuis_document(document, str(chemin))

    @classmethod
    def depuis_document(cls, document: object, origine: str) -> "Catalogue":
        """Le catalogue validé d'un objet JSON décodé. La moindre entrée fautive : `ValueError`.

        Une seule validation pour l'import et pour la relecture de la base : ce que l'import
        accepte est exactement ce que la tournée accepte, et une ligne corrigée à la main
        dans la base ne passe pas plus facilement qu'un fichier.

        Tout ou rien, et non une entrée fautive sautée : sautée, une catégorie privée mal
        écrite disparaîtrait du catalogue sans bruit, et c'est son propriétaire qui la
        perdrait, sans comprendre pourquoi.

        Un propriétaire inconnu de l'annuaire n'est pas une faute : la personne peut
        s'inscrire après que sa catégorie a été décrite.
        """
        if not isinstance(document, dict):
            raise ValueError(
                f"Catalogue {origine} : un objet JSON dont les clés sont les libellés "
                f"FreshRSS est attendu, pas {type(document).__name__}."
            )
        entrees = [
            _entree(libelle, valeur, origine)
            for libelle, valeur in document.items()
            if not _commentaire(libelle, valeur)
        ]
        if not entrees:
            # Vide, le catalogue retomberait sur « tout à tout le monde » : c'est
            # précisément ce qu'il existe pour empêcher.
            raise ValueError(f"Catalogue {origine} : aucune catégorie décrite.")
        try:
            return cls(entrees)
        except ValueError as exc:
            raise ValueError(f"Catalogue {origine} : {exc}") from exc


class CatalogueOuvert(Catalogue):
    """Aucun catalogue déclaré : tout est servi à tout le monde, comme avant le catalogue.

    N'est acceptable que pour une installation à une seule personne : c'est la tournée qui
    le vérifie (`Tournee._verifier_catalogue`), puisque c'est elle qui sait combien de
    personnes elle sert.
    """

    @property
    def ouvert(self) -> bool:
        return True

    def visible(self, categorie: str, username: str) -> bool:
        return True

    def hors_catalogue(self, categories: list[str]) -> list[str]:
        return []

    def proposables(self, username: str) -> list[CategorieCatalogue]:
        """Aucune : sans catalogue, rien ne dit quelles catégories existent, et tout est
        déjà suivi, il n'y a rien à cocher."""
        return []

    def abonnement(
        self,
        categories: Iterable[str],
        username: str,
        origine: str,
        acquises: Iterable[str] = (),
    ) -> tuple[str, ...]:
        """Telles que déclarées : sans catalogue, rien ne dit quels libellés existent."""
        return tuple(categories)


def cle_categorie(libelle: str) -> str:
    """La forme sous laquelle deux libellés se comparent : rognée, sans casse ni accents.

    La même des deux côtés, le libellé décrit, rogné à la lecture, et celui que FreshRSS
    renvoie, sans quoi un espace de trop d'un seul côté suffirait à fermer la catégorie.
    """
    return casefold_ascii(libelle.strip())


def _commentaire(libelle: object, valeur: object) -> bool:
    """Vrai pour une clé de commentaire : `_` en tête, et une valeur qui n'est pas un objet.

    La valeur tranche, pas le seul préfixe : une vraie catégorie FreshRSS peut s'appeler
    `_Archive`, et l'ignorer la ferait disparaître du catalogue sans un mot.
    """
    return (
        isinstance(libelle, str)
        and libelle.startswith(PREFIXE_COMMENTAIRE)
        and not isinstance(valeur, dict)
    )


def _entree(libelle: object, valeur: object, origine: str) -> CategorieCatalogue:
    """Une entrée du document, validée ; le message nomme le libellé fautif."""
    if not isinstance(libelle, str) or not libelle.strip():
        raise ValueError(f"Catalogue {origine} : libellé de catégorie vide.")
    lieu = f"Catalogue {origine}, « {libelle} »"
    if not isinstance(valeur, dict):
        raise ValueError(f"{lieu} : un objet JSON est attendu, pas {type(valeur).__name__}.")

    inconnues = sorted(cle for cle in valeur if cle not in CLES)
    if inconnues:
        raise ValueError(
            f"{lieu} : clé(s) inconnue(s) {', '.join(inconnues)}. "
            f"Clés acceptées : {', '.join(CLES)}."
        )

    description = valeur.get(CLE_DESCRIPTION)
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{lieu} : « {CLE_DESCRIPTION} » est un texte non vide.")

    metiers = valeur.get(CLE_METIERS)
    if not isinstance(metiers, list) or not all(
        isinstance(metier, str) and metier.strip() for metier in metiers
    ):
        raise ValueError(f"{lieu} : « {CLE_METIERS} » est une liste de textes non vides.")

    visibilite = valeur.get(CLE_VISIBILITE)
    if visibilite not in VISIBILITES:
        raise ValueError(
            f"{lieu} : « {CLE_VISIBILITE} » vaut {' ou '.join(VISIBILITES)}, pas « {visibilite} »."
        )

    proprietaires = valeur.get(CLE_PROPRIETAIRES)
    if visibilite == VISIBILITE_PUBLIQUE:
        if proprietaires:
            raise ValueError(
                f"{lieu} : une catégorie publique n'a pas de « {CLE_PROPRIETAIRES} », "
                f"la déclarer {VISIBILITE_PRIVEE}, ou retirer la liste."
            )
        proprietaires = []
    elif not isinstance(proprietaires, list) or not proprietaires:
        raise ValueError(
            f"{lieu} : une catégorie privée nomme ses « {CLE_PROPRIETAIRES} », une liste "
            "de noms de profil."
        )
    for proprietaire in proprietaires:
        try:
            valider_username(proprietaire)
        except ValueError as exc:
            raise ValueError(f"{lieu} : {exc}") from exc

    return CategorieCatalogue(
        libelle.strip(),
        description.strip(),
        [metier.strip() for metier in metiers],
        proprietaires,
    )
