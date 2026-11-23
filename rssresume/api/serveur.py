"""Le serveur HTTP de l'API : authentification, corps JSON, envoi des audios en flux.

`http.server` et non un framework : l'image n'embarque pas pip, et l'API n'a que neuf
routes, toutes derrière un même jeton. `ThreadingHTTPServer` sert chaque requête dans son
fil — un audio long à télécharger ne bloque pas la liste des profils.

L'API n'est pas exposée sur Internet : seul le site l'appelle, par le réseau interne du
déploiement. Le jeton n'en est pas moins exigé partout — un réseau interne finit toujours
par accueillir un conteneur de plus.
"""

from __future__ import annotations

import hmac
import json
import os
import pathlib
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rssresume.annuaire_sqlite import AnnuaireSqlite
from rssresume.api.routes import ROUTES, ErreurApi, Route
from rssresume.api.sorties import Audio, Sorties
from rssresume.config import ENV_API_TOKEN, ENV_TIMEZONE, load_timezone
from rssresume.desabonnement import OBJET_DESABONNEMENT, Desabonnement, Signataire
from rssresume.profil import ENV_PROFILES_DB, Annuaire
from rssresume.scheduler import DailySchedule, parse_schedule
from rssresume.tools import console
from rssresume.gabarits import CHEMIN_BUILTIN, Gabarits

ENV_API_HOST = "RSSRESUME_API_HOST"
ENV_API_PORT = "RSSRESUME_API_PORT"
DEFAULT_API_HOST = "0.0.0.0"
DEFAULT_API_PORT = 8080
#: Un jeton plus court se devine ; `secrets.token_urlsafe(48)` en donne 64 caractères.
LONGUEUR_MIN_JETON = 32
#: Un profil fait quelques kilo-octets. Au-delà, ce n'est pas un profil, et le lire en
#: mémoire pour le refuser ensuite serait déjà lui céder.
TAILLE_MAX_CORPS = 64 * 1024
#: La taille des blocs d'un audio envoyé en flux : jamais le fichier entier en mémoire.
TAILLE_BLOC = 64 * 1024

_MOTIF_PLAGE = re.compile(r"(\d*)-(\d*)")


def valider_jeton(jeton: str | None) -> str:
    """Le jeton s'il est utilisable ; sinon `ValueError`, et le serveur ne démarre pas.

    Démarrer sans jeton, ou avec un jeton court, publierait les profils de tout le monde
    à quiconque atteint le port : le refus doit se voir au déploiement.
    """
    jeton = (jeton or "").strip()
    if len(jeton) < LONGUEUR_MIN_JETON:
        raise ValueError(
            f"{ENV_API_TOKEN} absente ou trop courte ({len(jeton)} caractère(s), "
            f"{LONGUEUR_MIN_JETON} au moins). En générer une : "
            'python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    return jeton


class PlageInsatisfiable(Exception):
    """La plage demandée tombe hors du fichier : 416."""


class Plage:
    """Une plage d'octets demandée par `Range`, bornes incluses."""

    def __init__(self, debut: int, fin: int):
        self.debut = debut
        self.fin = fin

    @property
    def longueur(self) -> int:
        return self.fin - self.debut + 1

    @classmethod
    def depuis_entete(cls, entete: str | None, taille: int) -> "Plage | None":
        """La plage d'un en-tête `Range`, ou `None` pour envoyer le fichier entier.

        Un en-tête illisible ou multiple est ignoré, comme le permet la RFC 9110 : le
        fichier entier est une réponse correcte à toute demande de plage. Seule une plage
        lisible mais hors du fichier est une erreur.
        """
        if not entete or not entete.startswith("bytes=") or "," in entete:
            return None
        correspondance = _MOTIF_PLAGE.fullmatch(entete[len("bytes="):].strip())
        if correspondance is None or correspondance.group(0) == "-":
            return None
        debut, fin = correspondance.groups()
        if not debut:
            suffixe = int(fin)
            if suffixe == 0 or taille == 0:
                raise PlageInsatisfiable
            return cls(max(0, taille - suffixe), taille - 1)
        debut = int(debut)
        if fin and int(fin) < debut:
            return None
        if debut >= taille:
            raise PlageInsatisfiable
        return cls(debut, min(int(fin), taille - 1) if fin else taille - 1)


class ApplicationApi:
    """Ce que le serveur sert : le jeton attendu, et les routes montées sur les profils."""

    def __init__(
        self,
        jeton: str,
        annuaire: AnnuaireSqlite,
        sorties: Sorties,
        passage: DailySchedule | None = None,
    ):
        jeton = valider_jeton(jeton)
        self._jeton = jeton.encode("utf-8")
        # Sans planning donné, celui qu'aurait le travailleur sans aucune variable : l'API
        # n'annonce jamais une heure que le passage ne tiendrait pas.
        passage = passage or DailySchedule(parse_schedule(None), load_timezone(None))
        catalogue = annuaire.catalogue()
        gabarits = Gabarits.depuis_fichier(CHEMIN_BUILTIN, None if catalogue.ouvert else catalogue)
        # Le même secret que celui du travailleur, qui signe les liens de la lettre : c'est
        # le jeton de l'API, que les deux lisent dans le même environnement.
        desabonnement = Desabonnement(Signataire(jeton, OBJET_DESABONNEMENT))
        self.routes: list[Route] = [
            route(annuaire, sorties, passage, gabarits, desabonnement) for route in ROUTES
        ]

    @classmethod
    def from_env(cls) -> "ApplicationApi":
        """L'application que l'environnement décrit. Incomplet : `ValueError`, au lancement.

        Le planning est relu des mêmes variables que le travailleur, et une heure illisible
        arrête le démarrage comme elle arrête le sien : annoncer au site un passage que le
        travailleur ne fera pas serait pire que de ne rien annoncer.
        """
        jeton = valider_jeton(os.getenv(ENV_API_TOKEN))
        annuaire = Annuaire.depuis_env()
        if not isinstance(annuaire, AnnuaireSqlite):
            raise ValueError(
                f"L'API n'édite que la base de profils : poser {ENV_PROFILES_DB} "
                "(par exemple /data/profils.sqlite3)."
            )
        sorties = Sorties(pathlib.Path((os.getenv("RSSRESUME_OUTPUT_DIR") or "").strip() or "output"))
        passage = DailySchedule.from_env(load_timezone(os.getenv(ENV_TIMEZONE)))
        return cls(jeton, annuaire, sorties, passage)

    def authentifie(self, entete: str | None) -> bool:
        """Vrai pour `Bearer <jeton>`. Comparaison à temps constant : la durée d'un refus
        ne doit rien dire du nombre de caractères justes."""
        if not entete or not entete.startswith("Bearer "):
            return False
        return hmac.compare_digest(entete[len("Bearer "):].strip().encode("utf-8"), self._jeton)

    def trouver(self, chemin: str) -> tuple[Route, list[str]]:
        for route in self.routes:
            parametres = route.parametres(chemin)
            if parametres is not None:
                return route, parametres
        raise ErreurApi(404, "Ressource inconnue.")


class GestionnaireApi(BaseHTTPRequestHandler):
    """Une requête : authentifiée, routée, et sa réponse écrite.

    HTTP/1.1, pour que le lecteur audio garde sa connexion d'une plage à la suivante. Toute
    réponse porte donc sa longueur ; et une réponse donnée sans avoir lu le corps ferme la
    connexion, sans quoi le corps resté dans le tuyau serait lu comme la requête suivante.
    """

    protocol_version = "HTTP/1.1"
    server_version = "RSSResume"
    sys_version = ""
    server: "ServeurApi"

    def do_GET(self):
        self._traiter(lambda route, parametres: route.get(self, *parametres))

    def do_POST(self):
        self._traiter(lambda route, parametres: route.post(self, *parametres))

    def do_PUT(self):
        self._traiter(lambda route, parametres: route.put(self, *parametres))

    def do_DELETE(self):
        self._traiter(lambda route, parametres: route.delete(self, *parametres))

    def _traiter(self, appel) -> None:
        self._corps_lu = False
        application = self.server.application
        try:
            if not application.authentifie(self.headers.get("Authorization")):
                raise ErreurApi(401, "Authentification requise.", {"WWW-Authenticate": "Bearer"})
            route, parametres = application.trouver(urllib.parse.urlsplit(self.path).path)
            appel(route, parametres)
        except ErreurApi as erreur:
            self._repondre_erreur(erreur)
        except Exception as exc:  # noqa: BLE001 — une requête perdue, pas le serveur
            console.error(f"API : erreur sur {self.command} {self._chemin_journal()} : {exc!r}")
            self._repondre_erreur(ErreurApi(500, "Erreur interne."))

    # --- Ce que les routes appellent -------------------------------------------------

    def corps_json(self) -> object:
        """Le corps décodé. Absent, trop gros, pas JSON : `ErreurApi`, avant toute lecture
        quand c'est possible."""
        if self.headers.get("Transfer-Encoding"):
            raise ErreurApi(400, "Corps en morceaux non accepté : envoyer Content-Length.")
        try:
            longueur = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ErreurApi(400, "Content-Length requis.") from None
        if longueur < 0:
            raise ErreurApi(400, "Content-Length invalide.")
        if longueur > TAILLE_MAX_CORPS:
            raise ErreurApi(413, f"Corps trop volumineux ({TAILLE_MAX_CORPS // 1024} Kio au plus).")
        if self.headers.get_content_type() != "application/json":
            raise ErreurApi(400, "Content-Type: application/json attendu.")
        brut = self.rfile.read(longueur)
        self._corps_lu = True
        try:
            return json.loads(brut.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErreurApi(400, f"JSON invalide : {exc}") from exc

    def repondre_json(self, statut: int, objet: object, entetes: dict[str, str] | None = None) -> None:
        corps = json.dumps(objet, ensure_ascii=False).encode("utf-8")
        self.send_response(statut)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self._fin_entetes()
        self.wfile.write(corps)

    def repondre_vide(self, statut: int) -> None:
        self.send_response(statut)
        self.send_header("Content-Length", "0")
        self._fin_entetes()

    def envoyer_audio(self, audio: Audio) -> None:
        """L'audio, entier ou sur la plage demandée, lu et écrit par blocs."""
        try:
            plage = Plage.depuis_entete(self.headers.get("Range"), audio.taille)
        except PlageInsatisfiable:
            raise ErreurApi(
                416, "Plage hors du fichier.", {"Content-Range": f"bytes */{audio.taille}"}
            ) from None
        debut, longueur = (0, audio.taille) if plage is None else (plage.debut, plage.longueur)
        try:
            # Ouvert avant les en-têtes : un fichier disparu entre la liste et la lecture
            # doit encore pouvoir donner un 404, pas une réponse 200 tronquée.
            fichier = audio.chemin.open("rb")
        except OSError as exc:
            raise ErreurApi(404, "Audio introuvable.") from exc
        with fichier:
            self.send_response(200 if plage is None else 206)
            self.send_header("Content-Type", audio.type_mime)
            self.send_header("Content-Length", str(longueur))
            self.send_header("Accept-Ranges", "bytes")
            if plage is not None:
                self.send_header("Content-Range", f"bytes {plage.debut}-{plage.fin}/{audio.taille}")
            self._fin_entetes()
            self._copier(fichier, debut, longueur)

    def _copier(self, fichier, debut: int, longueur: int) -> None:
        """Recopie `longueur` octets depuis `debut`, bloc par bloc."""
        try:
            fichier.seek(debut)
            restant = longueur
            while restant > 0:
                bloc = fichier.read(min(TAILLE_BLOC, restant))
                if not bloc:
                    # Le fichier a raccourci depuis l'annonce de sa taille : la longueur
                    # promise ne sera pas tenue, la connexion ne peut pas resservir.
                    self.close_connection = True
                    break
                self.wfile.write(bloc)
                restant -= len(bloc)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Le lecteur a sauté plus loin et abandonné cette plage : c'est son usage normal.
            self.close_connection = True

    # --- Mécanique ------------------------------------------------------------------

    def _repondre_erreur(self, erreur: ErreurApi) -> None:
        if not self._corps_lu:
            self._ecarter_corps()
        self.repondre_json(erreur.statut, erreur.corps(), erreur.entetes)

    def _ecarter_corps(self) -> None:
        """Lit et jette un corps resté dans le tuyau, s'il est petit ; sinon ferme.

        Le petit corps est lu pour que la connexion resserve — un 401 ne doit pas coûter
        une reconnexion au site. Un gros n'est pas lu, c'est tout l'objet du 413.
        """
        texte = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            return
        if texte is None:
            return
        if texte.isdigit() and int(texte) <= TAILLE_MAX_CORPS:
            self.rfile.read(int(texte))
            self._corps_lu = True
            return
        self.close_connection = True

    def _fin_entetes(self) -> None:
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

    def _chemin_journal(self) -> str:
        """Le chemin sans la requête : rien de ce qui suit le `?` n'a à finir dans les logs."""
        return urllib.parse.urlsplit(self.path).path

    def log_request(self, code="-", size="-") -> None:
        """Une ligne sobre par requête. Ni en-têtes — le jeton y est —, ni chaîne de requête."""
        statut = getattr(code, "value", code)
        console.log(f"API {self.address_string()} {self.command} {self._chemin_journal()} {statut}")

    def log_error(self, format, *args) -> None:
        console.error(f"API {self.address_string()} : {format % args}")

    def log_message(self, format, *args) -> None:
        console.log(f"API {self.address_string()} : {format % args}")


class ServeurApi(ThreadingHTTPServer):
    """Le serveur, porteur de l'application que ses gestionnaires servent."""

    daemon_threads = True

    def __init__(self, adresse: tuple[str, int], application: ApplicationApi):
        self.application = application
        super().__init__(adresse, GestionnaireApi)


def adresse_depuis_env() -> tuple[str, int]:
    """L'adresse d'écoute. Un port illisible : `ValueError`, au lancement."""
    hote = (os.getenv(ENV_API_HOST) or "").strip() or DEFAULT_API_HOST
    texte = (os.getenv(ENV_API_PORT) or "").strip() or str(DEFAULT_API_PORT)
    if not texte.isdigit() or not 0 < int(texte) < 65536:
        raise ValueError(f"{ENV_API_PORT} : « {texte} » n'est pas un port.")
    return hote, int(texte)
