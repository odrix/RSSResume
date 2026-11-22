"""Les ressources de l'API, une classe par forme d'URL.

La base porte ce qui est commun — reconnaître son URL, refuser une méthode qu'elle ne
sert pas, retrouver le profil nommé — ; chaque sous-classe ne redéfinit que les méthodes
HTTP qu'elle sert. Les routes ne parlent pas HTTP elles-mêmes : elles lèvent `ErreurApi`
et rendent des objets, la requête (`serveur.GestionnaireApi`) se charge du reste.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from typing import TYPE_CHECKING

from rssresume.annuaire_sqlite import AnnuaireSqlite, Fiche, ProfilDejaPris, ProfilInconnu
from rssresume.api.sorties import Sorties
from rssresume.profil import username_valide, valider_username
from rssresume.scheduler import DailySchedule

if TYPE_CHECKING:
    from rssresume.api.serveur import GestionnaireApi

PREFIXE = "/api/v1"


class ErreurApi(Exception):
    """Une réponse d'erreur : son statut, et le message rendu sous `{"erreur": …}`."""

    def __init__(self, statut: int, message: str, entetes: dict[str, str] | None = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.entetes = entetes or {}


class Route:
    """Une forme d'URL et les méthodes qu'elle sert.

    `motif` capture des segments bruts ; ils sont décodés ici, après le découpage, pour
    qu'un `%2F` reste à l'intérieur de son segment au lieu d'en créer un nouveau.
    """

    motif: re.Pattern
    methodes: tuple[str, ...] = ()

    def __init__(self, annuaire: AnnuaireSqlite, sorties: Sorties, passage: DailySchedule, gabarits=None):
        self.annuaire = annuaire
        self.sorties = sorties
        self.passage = passage
        self.gabarits = gabarits

    def parametres(self, chemin: str) -> list[str] | None:
        """Les segments variables décodés, si `chemin` est de cette forme ; sinon `None`."""
        correspondance = self.motif.fullmatch(chemin)
        if correspondance is None:
            return None
        try:
            return [
                urllib.parse.unquote(segment, errors="strict") for segment in correspondance.groups()
            ]
        except UnicodeDecodeError as exc:
            raise ErreurApi(400, "URL mal encodée.") from exc

    def get(self, requete: "GestionnaireApi", *parametres: str) -> None:
        raise self._non_servie()

    def post(self, requete: "GestionnaireApi", *parametres: str) -> None:
        raise self._non_servie()

    def put(self, requete: "GestionnaireApi", *parametres: str) -> None:
        raise self._non_servie()

    def delete(self, requete: "GestionnaireApi", *parametres: str) -> None:
        raise self._non_servie()

    def _non_servie(self) -> ErreurApi:
        return ErreurApi(
            405, "Méthode non autorisée sur cette ressource.", {"Allow": ", ".join(self.methodes)}
        )

    def fiche(self, username: str) -> Fiche:
        """Le profil nommé dans l'URL. Un nom invalide est un profil inconnu, pas une faute
        de saisie : rien ne peut exister sous ce nom."""
        if not username_valide(username):
            raise ErreurApi(404, f"Profil inconnu : « {username} ».")
        try:
            return self.annuaire.fiche(username)
        except ProfilInconnu as exc:
            raise ErreurApi(404, str(exc)) from exc
        except ValueError as exc:
            raise ErreurApi(422, str(exc)) from exc


class RouteProfils(Route):
    """`/api/v1/profils` : la liste, et la création."""

    motif = re.compile(re.escape(PREFIXE) + r"/profils")
    methodes = ("GET", "POST")

    def get(self, requete, *parametres):
        requete.repondre_json(200, [fiche.resume_json() for fiche in self.annuaire.fiches()])

    def post(self, requete, *parametres):
        saisie = requete.corps_json()
        if not isinstance(saisie, dict):
            raise ErreurApi(422, "Un profil est un objet JSON.")
        try:
            fiche = self.annuaire.creer(valider_username(saisie.get("username")), saisie)
        except ProfilDejaPris as exc:
            raise ErreurApi(409, str(exc)) from exc
        except ValueError as exc:
            raise ErreurApi(422, str(exc)) from exc
        requete.repondre_json(
            201, fiche.complet_json(), {"Location": f"{PREFIXE}/profils/{fiche.username}"}
        )


class RouteProfil(Route):
    """`/api/v1/profils/{username}` : lire, remplacer, supprimer."""

    motif = re.compile(re.escape(PREFIXE) + r"/profils/([^/]+)")
    methodes = ("GET", "PUT", "DELETE")

    def get(self, requete, username):
        requete.repondre_json(200, self.fiche(username).complet_json())

    def put(self, requete, username):
        """Remplace le document. L'id et le nom ne changent pas : les envoyer différents
        est refusé plutôt qu'ignoré, pour que le site ne croie pas avoir renommé."""
        actuelle = self.fiche(username)
        saisie = requete.corps_json()
        if not isinstance(saisie, dict):
            raise ErreurApi(422, "Un profil est un objet JSON.")
        if saisie.get("username", username) != username:
            raise ErreurApi(422, "Le nom d'un profil ne se change pas.")
        if saisie.get("id", actuelle.id) != actuelle.id:
            raise ErreurApi(422, "L'identifiant d'un profil ne se change pas.")
        try:
            fiche = self.annuaire.modifier(username, saisie)
        except ProfilInconnu as exc:
            raise ErreurApi(404, str(exc)) from exc
        except ValueError as exc:
            raise ErreurApi(422, str(exc)) from exc
        requete.repondre_json(200, fiche.complet_json())

    def delete(self, requete, username):
        """Retire le profil de la base. Ses journées restent sur le disque : effacer des
        audios est irréversible, et une suppression par erreur se recrée avec le même id
        par l'import."""
        self.fiche(username)
        try:
            self.annuaire.supprimer(username)
        except ProfilInconnu as exc:
            raise ErreurApi(404, str(exc)) from exc
        requete.repondre_vide(204)


class RouteJournees(Route):
    """`/api/v1/profils/{username}/journees` : les journées produites, la plus récente d'abord."""

    motif = re.compile(re.escape(PREFIXE) + r"/profils/([^/]+)/journees")
    methodes = ("GET",)

    def get(self, requete, username):
        fiche = self.fiche(username)
        requete.repondre_json(200, [journee.en_json() for journee in self.sorties.journees(fiche.id)])


class RouteJournee(Route):
    """`/api/v1/profils/{username}/journees/{date}` : ce que la journée raconte."""

    motif = re.compile(re.escape(PREFIXE) + r"/profils/([^/]+)/journees/([^/]+)")
    methodes = ("GET",)

    def get(self, requete, username, date):
        fiche = self.fiche(username)
        contenu = self.sorties.contenu(fiche.id, date)
        if contenu is None:
            raise ErreurApi(404, "Journée introuvable.")
        requete.repondre_json(200, contenu.en_json())


class RoutePassage(Route):
    """`/api/v1/passage` : l'heure du passage quotidien, et le prochain.

    Servi par l'API parce que c'est elle qui partage l'environnement du travailleur : le
    site n'a pas à recopier un réglage qui, recopié, finirait par diverger.
    """

    motif = re.compile(re.escape(PREFIXE) + r"/passage")
    methodes = ("GET",)

    def get(self, requete, *parametres):
        prochain = self.passage.next_run(dt.datetime.now(self.passage.timezone))
        requete.repondre_json(
            200,
            {
                "heure": self.passage.heure.isoformat("minutes"),
                "fuseau": str(self.passage.timezone),
                "prochain": prochain.isoformat(timespec="seconds"),
            },
        )


class RouteAudio(Route):
    """`/api/v1/profils/{username}/journees/{date}/audios/{nom}` : un audio, en flux."""

    motif = re.compile(re.escape(PREFIXE) + r"/profils/([^/]+)/journees/([^/]+)/audios/([^/]+)")
    methodes = ("GET",)

    def get(self, requete, username, date, nom):
        fiche = self.fiche(username)
        audio = self.sorties.audio(fiche.id, date, nom)
        if audio is None:
            raise ErreurApi(404, "Audio introuvable.")
        requete.envoyer_audio(audio)


class RouteGabarits(Route):
    """`/api/v1/gabarits` : les modèles de profil proposés au site."""

    motif = re.compile(re.escape(PREFIXE) + r"/gabarits")
    methodes = ("GET",)

    def get(self, requete, *parametres):
        requete.repondre_json(200, [gabarit.en_json() for gabarit in self.gabarits])


#: Les routes servies, dans l'ordre où elles sont essayées.
ROUTES = (RouteProfils, RouteProfil, RouteJournees, RouteJournee, RouteAudio, RoutePassage, RouteGabarits)
