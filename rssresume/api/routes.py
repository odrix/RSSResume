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

from rssresume.annuaire_sqlite import (
    AnnuaireSqlite,
    CatalogueIllisible,
    Fiche,
    ProfilDejaPris,
    ProfilInconnu,
)
from rssresume.api.sorties import Sorties
from rssresume.desabonnement import Demande, Desabonnement, JetonInvalide
from rssresume.profil import CLE_EMAIL, ChampInvalide, username_valide, valider_username
from rssresume.scheduler import DailySchedule
from rssresume.tools import console

if TYPE_CHECKING:
    from rssresume.api.serveur import GestionnaireApi

PREFIXE = "/api/v1"


class ErreurApi(Exception):
    """Une réponse d'erreur : son statut, et le message rendu sous `{"erreur": …}`.

    `champ` nomme la clé du document en cause quand la validation la connaît : le site
    affiche alors le refus sous ce champ, au lieu de le deviner d'après le message.
    """

    def __init__(
        self,
        statut: int,
        message: str,
        entetes: dict[str, str] | None = None,
        champ: str | None = None,
    ):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.entetes = entetes or {}
        self.champ = champ

    @classmethod
    def refus(cls, exc: ValueError) -> "ErreurApi":
        """La réponse d'un document refusé : 422, avec sa clé fautive quand elle est connue.

        Un catalogue illisible n'est pas un refus de la saisie, mais une base à réparer : 500,
        journalisée pour l'exploitant, sans rien montrer à la personne qu'elle puisse corriger.
        """
        if isinstance(exc, CatalogueIllisible):
            console.error(f"API : catalogue des catégories illisible : {exc}")
            return cls(500, "Le catalogue des catégories est illisible.")
        return cls(422, str(exc), champ=exc.champ if isinstance(exc, ChampInvalide) else None)

    def corps(self) -> dict:
        """Le corps JSON de la réponse. `champ` n'y est que s'il est connu : un refus qui ne
        tient pas à une clé (un corps qui n'est pas un objet) n'a pas de case où s'afficher."""
        corps = {"erreur": self.message}
        if self.champ:
            corps["champ"] = self.champ
        return corps


class Route:
    """Une forme d'URL et les méthodes qu'elle sert.

    `motif` capture des segments bruts ; ils sont décodés ici, après le découpage, pour
    qu'un `%2F` reste à l'intérieur de son segment au lieu d'en créer un nouveau.
    """

    motif: re.Pattern
    methodes: tuple[str, ...] = ()

    def __init__(
        self,
        annuaire: AnnuaireSqlite,
        sorties: Sorties,
        passage: DailySchedule,
        gabarits=None,
        desabonnement: Desabonnement | None = None,
    ):
        self.annuaire = annuaire
        self.sorties = sorties
        self.passage = passage
        self.gabarits = gabarits
        self.desabonnement = desabonnement

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


#: La seule réponse d'un lien de désabonnement refusé, quelle qu'en soit la raison : qui
#: tient un jeton n'a pas à apprendre si le profil existe, ni si la signature était bonne.
LIEN_DESABONNEMENT_INVALIDE = "Lien de désabonnement invalide ou déjà utilisé."


class _RouteDesabonnement(Route):
    """Ce que les deux routes du désabonnement partagent : relire le jeton du corps.

    Le jeton voyage dans un corps JSON et non dans l'URL : les journaux d'accès notent
    les chemins, et un lien encore valable n'a rien à y faire.
    """

    methodes = ("POST",)

    def demande(self, requete: "GestionnaireApi") -> Demande:
        corps = requete.corps_json()
        jeton = corps.get("jeton") if isinstance(corps, dict) else None
        if not isinstance(jeton, str) or self.desabonnement is None:
            raise ErreurApi(404, LIEN_DESABONNEMENT_INVALIDE)
        try:
            return self.desabonnement.lire(jeton)
        except JetonInvalide as exc:
            raise ErreurApi(404, LIEN_DESABONNEMENT_INVALIDE) from exc


class RouteDesabonnementLecture(_RouteDesabonnement):
    """`/api/v1/desabonnements/lecture` : ce que le lien désabonnerait, sans rien changer.

    Un POST qui ne modifie rien, pour garder le jeton hors de l'URL. La page du site
    l'appelle à l'affichage : un antivirus de messagerie qui ouvre le lien ne doit pas
    désabonner à la place de la personne.
    """

    motif = re.compile(re.escape(PREFIXE) + r"/desabonnements/lecture")

    def post(self, requete, *parametres):
        demande = self.demande(requete)
        try:
            fiche = self.annuaire.fiche_par_id(demande.profil_id)
        except ValueError:
            fiche = None
        emails = list(fiche.document.get(CLE_EMAIL, [])) if fiche else []
        if fiche is None or not demande.concerne(emails):
            raise ErreurApi(404, LIEN_DESABONNEMENT_INVALIDE)
        requete.repondre_json(200, {"username": fiche.username, "destinataires": len(emails)})


class RouteDesabonnements(_RouteDesabonnement):
    """`/api/v1/desabonnements` : vide les destinataires du profil que le lien désigne.

    Tout le profil et non une adresse : la lettre part en un seul envoi, à tous les
    destinataires ensemble, et rien ne dit lequel a cliqué.
    """

    motif = re.compile(re.escape(PREFIXE) + r"/desabonnements")

    def post(self, requete, *parametres):
        fiche = self.annuaire.desabonner(self.demande(requete))
        if fiche is None:
            raise ErreurApi(404, LIEN_DESABONNEMENT_INVALIDE)
        requete.repondre_json(200, {"username": fiche.username})


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
            raise ErreurApi.refus(exc) from exc
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
            raise ErreurApi.refus(exc) from exc
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


class RouteCategoriesProposees(Route):
    """`/api/v1/profils/{username}/categories` : les catégories que la page profil propose.

    Calculées ici, par `Catalogue.proposables`, et non filtrées par le site : la règle de
    visibilité est celle qui refusera l'enregistrement, et une catégorie privée d'autrui ne
    doit jamais quitter l'API, même pour être masquée.

    Le profil n'a pas besoin d'exister : la page s'affiche avant le premier enregistrement,
    qui le crée. Un nom invalide reste un 404, rien ne pouvant exister sous ce nom.
    """

    motif = re.compile(re.escape(PREFIXE) + r"/profils/([^/]+)/categories")
    methodes = ("GET",)

    def get(self, requete, username):
        if not username_valide(username):
            raise ErreurApi(404, f"Profil inconnu : « {username} ».")
        try:
            catalogue = self.annuaire.catalogue()
        except CatalogueIllisible as exc:
            raise ErreurApi.refus(exc) from exc
        requete.repondre_json(
            200,
            {
                "ouvert": catalogue.ouvert,
                "categories": [entree.proposition_json() for entree in catalogue.proposables(username)],
            },
        )


#: Les routes servies, dans l'ordre où elles sont essayées.
ROUTES = (
    RouteDesabonnementLecture,
    RouteDesabonnements,
    RouteProfils,
    RouteProfil,
    RouteJournees,
    RouteJournee,
    RouteAudio,
    RoutePassage,
    RouteGabarits,
    RouteCategoriesProposees,
)
