"""Le document d'une personne : son profil de pertinence, sa stack, son destinataire.

Le profil de pertinence est le seul élément vraiment personnel du système. Il est
utilisé par les trois prompts — noter, résumer un article, dicter le digest audio — et
c'est lui qui décide de tout le reste : ce qui monte au-dessus du seuil, ce qui est
raconté, et sous quel angle. Ses clés `axes` personnalisent aussi les rubriques du
scoring et changent l'empreinte de cache : ouvrir l'outil à quelqu'un d'autre peut donc
changer ce texte, ses axes, ou les deux.

Les deux autres sont personnelles pour la même raison, et se lisent au même endroit :
ce qu'on exploite (la liste de composants sur laquelle les avis CERT-FR sont appariés)
et à qui le digest est envoyé. Trois fichiers et trois variables d'environnement pour un
seul lecteur n'avaient d'autre effet que de multiplier les chemins à tenir — un seul
document, hors du dépôt, en dit autant :

    {"profil": "CTO d'un SaaS…", "stack": ["Traefik"], "email": "moi@example.com"}

La clé `securite` y règle, pour la même raison, le détail dont la personne a besoin sur
les vulnérabilités : `exploitant` (le défaut), `decideur` ou `curieux`. Qui n'administre
rien n'a que faire des plages de versions, et c'est son document, non le modèle, qui le
dit.

La clé `categories` y liste les catégories suivies — publiques, ou privées dont la
personne est propriétaire : `"categories": ["Tech", "Veille marché"]`. Absente, la
personne reçoit tout ce que le catalogue lui autorise. Ce qu'elle ne suit pas n'est ni
noté ni résumé pour elle : c'est le premier filtre, et le moins cher.

La clé `flux_exclus` descend d'un cran, au flux : `"flux_exclus": ["NoLimitSecu"]`. Une
catégorie suivie mêle des flux qui se résument et d'autres qui ne le peuvent pas — un
podcast sans transcription, un journal des versions — et les noter coûte des tokens pour
un résultat vide. Leurs articles ne sont ni notés ni résumés, mais sont marqués lus avec
le reste : ce qu'on a choisi de ne pas lire n'a pas à revenir le lendemain.

Il est donc chargé, pas codé en dur au point d'appel : un profil explicite passé en
argument, sinon l'environnement, sinon le profil par défaut ci-dessous. Ce défaut ne
décrit personne : il vaut pour quelqu'un dans la tech, sans dire de quel produit ni de
quelle équipe.

Plusieurs personnes lisent maintenant le même FreshRSS : un dossier de documents, un par
personne, nommé d'après elle (`RSSRESUME_PROFILES_DIR`, voir `Annuaire`). Le nom du
fichier — le `username` — n'est pas une étiquette décorative : il nomme le répertoire de
sortie et préfixe les tags FreshRSS. C'est pourquoi il est contraint, et pourquoi un
fichier mal nommé est une erreur et non un profil de plus.

Ce module est aussi lu par le site qui édite les profils : la validation d'un document
(`profil_depuis_dict`) et celle d'un nom (`valider_username`) y sont publiques, pour qu'il
n'existe qu'une seule idée de ce qu'est un profil acceptable.
"""

from __future__ import annotations

import enum
import json
import os
import pathlib
import re
import uuid
from typing import TYPE_CHECKING, Iterable

from rssresume.certfr.stack import CLE_STACK, Stack, StackError
from rssresume.axes import Axes, AxesError, CLE_AXES
from rssresume.tools import console
from rssresume.tools.text import casefold_ascii

if TYPE_CHECKING:
    from rssresume.categories import Catalogue
    from rssresume.models import Article

#: Le texte du profil seul, pour un profil court. Ne porte ni stack ni destinataire :
#: une valeur d'environnement est une ligne, pas un document.
ENV_PROFIL = "RSSRESUME_PROFILE"
#: Le chemin du document, c'est-à-dire le cas d'une installation à une seule personne.
ENV_PROFIL_FILE = "RSSRESUME_PROFILE_FILE"
#: Le dossier des documents, un `{username}.json` par personne. Exclusif des deux
#: variables précédentes : voir `Annuaire.depuis_env`.
ENV_PROFILES_DIR = "RSSRESUME_PROFILES_DIR"
#: La base SQLite des profils, celle qu'édite l'API (`annuaire_sqlite.AnnuaireSqlite`).
#: Exclusive des trois variables précédentes, pour la même raison que le dossier.
ENV_PROFILES_DB = "RSSRESUME_PROFILES_DB"

#: Un nom court, en minuscules, sans point ni espace : il devient un nom de répertoire
#: et un préfixe de label FreshRSS, deux endroits où une majuscule ou un espace ne se
#: relisent pas de la même façon partout.
MOTIF_USERNAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
#: L'extension d'un document du dossier. Les autres fichiers (un README, un `.gitkeep`)
#: ne sont pas des profils et sont ignorés.
EXTENSION_PROFIL = ".json"

#: Les clés du document. `profil` est la seule exigée.
CLE_PROFIL = "profil"
#: L'identifiant stable de la personne, un UUID. Le `username` est le nom humain — il
#: préfixe les tags et se tape dans `--profil` —, l'`id` nomme la sortie : renommer
#: quelqu'un ne doit pas le séparer de ses journées. Absent d'un document du dossier, il
#: est généré et écrit dans le fichier au premier passage.
CLE_ID = "id"
CLE_EMAIL = "email"
#: Le prénom, pour la salutation de l'audio de journée. Il est ici et pas ailleurs pour
#: la même raison que l'adresse : comment on s'adresse à quelqu'un est aussi personnel
#: que ce qu'il veut lire, et rien de personnel ne se déclare dans l'environnement.
CLE_PRENOM = "prenom"
#: Le régime de sécurité : ce que la personne a besoin d'entendre d'une vulnérabilité.
CLE_SECURITE = "securite"
#: Les catégories suivies. Que chacune existe et soit permise à la personne, seul le
#: catalogue le sait : ce module n'en vérifie que la forme (`categories.Catalogue.abonnement`
#: fait le reste).
CLE_CATEGORIES = "categories"
#: Les flux dont les articles ne sont ni notés ni résumés, nommés par leur titre FreshRSS.
CLE_FLUX_EXCLUS = "flux_exclus"


class FluxExclus:
    """Les flux qu'une personne retire du scoring et du résumé, nommés par leur titre.

    Par flux et non par catégorie : la catégorie se règle déjà par l'abonnement, et ce
    qui ne se résume pas est un flux précis au milieu d'autres qui se résument très bien.

    L'appariement est une égalité, pas une inclusion : « Go » exclurait sinon « Google
    Cloud Blog », et un flux écarté en silence ne se remarque qu'à son absence. Casse et
    accents retirés, comme le catalogue compare : un titre recopié à la main perd les
    siens en route, et n'apparierait plus rien sans que rien ne le dise.
    """

    def __init__(self, titres: Iterable[str] = ()) -> None:
        #: Les titres tels que déclarés : c'est eux que le document relit et que le
        #: journal montre, pas leur forme repliée.
        self.titres = tuple(titres)
        self._replies = frozenset(casefold_ascii(titre.strip()) for titre in self.titres)

    @classmethod
    def declares(cls, valeur: object, origine: str) -> "FluxExclus":
        """Les flux déclarés, rognés ; aucun si la clé manque. Mal formés : `ValueError`.

        La liste vide est acceptée, contrairement à `categories` : n'exclure aucun flux
        est l'état ordinaire, et une liste vidée dans le formulaire veut dire exactement
        cela. Un doublon est refusé comme pour les catégories — il dirait deux fois la
        même chose, et le second masquerait une faute de recopie.
        """
        if valeur is None:
            return cls()
        if not isinstance(valeur, list):
            raise ValueError(
                f"{origine} : « {CLE_FLUX_EXCLUS} » est une liste de titres de flux, "
                f"pas {type(valeur).__name__}."
            )
        vus: dict[str, str] = {}
        for titre in valeur:
            if not isinstance(titre, str) or not titre.strip():
                raise ValueError(
                    f"{origine} : « {CLE_FLUX_EXCLUS} » ne contient que des titres de flux "
                    f"non vides, pas « {titre} »."
                )
            cle = casefold_ascii(titre.strip())
            if cle in vus:
                raise ValueError(
                    f"{origine} : « {CLE_FLUX_EXCLUS} » nomme deux fois le même flux "
                    f"(« {vus[cle]} » et « {titre.strip()} »)."
                )
            vus[cle] = titre.strip()
        return cls(vus.values())

    def exclut(self, article: "Article") -> bool:
        """Vrai quand l'article vient d'un flux exclu. Le titre du flux, jamais la catégorie."""
        return casefold_ascii(article.feed_title.strip()) in self._replies

    def __bool__(self) -> bool:
        return bool(self._replies)

    def en_document(self) -> list[str]:
        """La forme d'échange, celle que le document stocké relit telle quelle."""
        return list(self.titres)


class Securite(enum.Enum):
    """Le détail que les vulnérabilités méritent, selon ce que la personne fait d'elles.

    Une énumération et non un texte libre : le régime choisit une consigne écrite à
    l'avance, et une valeur que personne n'a prévue n'en choisirait aucune. Le choix se
    fait dans le code, comme pour la stack déclarée — le laisser au modèle, ce serait lui
    demander de deviner ce qu'un profil en prose sous-entend.
    """

    #: Administre ce qui tourne : les versions, graduées sur la stack s'il y en a une.
    EXPLOITANT = "exploitant"
    #: Décide sans appliquer les correctifs : une phrase par faille, sans versions, sauf
    #: sur un composant de sa stack.
    DECIDEUR = "decideur"
    #: Suit la sécurité de loin : seulement ce qui est exploité ou fait l'actualité.
    CURIEUX = "curieux"

    @classmethod
    def depuis_document(cls, valeur: object, origine: str) -> "Securite":
        """Le régime déclaré, ou le défaut si la clé manque. Autre chose : `ValueError`.

        Pas de normalisation de casse : un document se corrige une fois, au lancement,
        alors qu'une tolérance devrait se répéter dans chaque lecteur — le site compris.
        """
        if valeur is None:
            return SECURITE_PAR_DEFAUT
        for regime in cls:
            if isinstance(valeur, str) and valeur == regime.value:
                return regime
        raise ValueError(
            f"{origine} : « {CLE_SECURITE} » vaut exploitant, decideur ou curieux, pas « {valeur} »."
        )


#: Le seul endroit où vit le défaut : le régime d'avant la clé, pour qu'un document qui
#: ne la porte pas soit servi exactement comme la veille.
SECURITE_PAR_DEFAUT = Securite.EXPLOITANT

DEFAULT_PROFIL = """Professionnel de la tech — développement, produit, direction technique
ou qualité. Veille quotidienne sur ce qui change la façon de concevoir, de livrer et
d'exploiter un logiciel, et sur ce qui oblige à décider.

Axes de veille pertinents :
- reglementaire : ce que la loi impose au logiciel et aux données (RGPD, NIS2, DORA,
  AI Act, accessibilité), les référentiels et les décisions qui font jurisprudence.
- cyber : cybersécurité technique (failles exploitables sur des composants répandus,
  chiffrement, gestion de clés, chaîne d'approvisionnement logicielle, incidents
  majeurs et ce qu'ils apprennent).
- marche : les acteurs et les outils du métier — rachats, fermetures de service,
  changements de modèle économique ou de licence qui obligent à migrer.
- stack : veille technologique (langages, frameworks, bases de données, conteneurs,
  cloud, observabilité) : versions majeures, fins de support, ruptures de
  compatibilité. Et l'économie de cette infrastructure : tarifs des hébergeurs et des
  clouds, coûts de stockage et de bande passante, frais de sortie, changements de
  facturation. Un tarif qui bouge se suit comme une décision.
- autre : la façon de faire de la tech et de la faire faire. Pratiques de
  développement et d'ingénierie (méthodes, revue de code, tests, dette technique,
  productivité d'une équipe, retours d'expérience d'autres équipes techniques), et
  management humain : recrutement, fidélisation, rapport au travail des nouvelles
  générations, organisation d'une équipe technique, et surtout la conduite du
  changement quand une technologie majeure arrive.

Ne sont PAS pertinents : le hardware grand public, les levées de fonds sans conséquence
technique, les annonces produit sans impact sur ce qu'on exploite, et l'actualité IA
grand public — usages consumer, démonstrations, classements de modèles. L'IA reste
pertinente sur deux terrains seulement : ce qu'elle change à la sécurité et à la
conformité, et ce qu'elle change à la façon de développer et d'encadrer une équipe."""


class Profil:
    """Ce qu'une personne apporte au digest, et rien d'autre.

    Objet et non trois valeurs rendues ensemble : les trois voyagent d'un seul tenant
    du fichier jusqu'à `AppConfig`, et c'est ici qu'on lit ce qu'est un lecteur du
    digest — un critère de pertinence, une infrastructure, une boîte aux lettres.
    """

    def __init__(
        self,
        texte: str,
        stack: Stack | None = None,
        emails: Iterable[str] = (),
        prenom: str = "",
        identifiant: str = "",
        securite: Securite = SECURITE_PAR_DEFAUT,
        axes: Axes | None = None,
        categories: Iterable[str] | None = None,
        flux_exclus: FluxExclus | None = None,
    ):
        #: L'identifiant stable de la personne (un UUID), qui nomme son répertoire de
        #: sortie. Vide tant que le document n'en porte pas : c'est l'annuaire qui le
        #: génère et l'écrit, pas la lecture d'un document.
        self.id = identifiant
        self.texte = texte
        #: Les axes personnalisent les rubriques du scoring. Absents du document, ils
        #: restent les cinq thématiques d'origine — leur empreinte doit donc rester identique.
        self.axes = axes if axes is not None else Axes.par_defaut()
        #: Vide quand le document ne déclare rien : aucun avis n'est alors apparié, et
        #: la phrase du digest le dit plutôt que d'annoncer que rien ne nous concerne.
        self.stack = stack if stack is not None else Stack()
        #: Les destinataires du digest. Vides, aucun email ne part — c'est déjà ce que
        #: faisait `SMTP_TO` absente.
        self.emails = tuple(emails)
        #: Le prénom qui ouvre l'audio de journée. Vide, le montage n'appelle personne
        #: par son nom : c'est une salutation en moins, pas une erreur.
        self.prenom = prenom
        #: Le détail dû aux vulnérabilités. Il voyage avec la stack, parce que c'est elle
        #: qu'il module : une stack dit ce qui tourne, le régime dit qui l'écoute.
        self.securite = securite
        #: Les catégories suivies, telles que déclarées. `None` — clé absente — et non un
        #: tuple vide : l'absence veut dire « tout ce que le catalogue autorise », et doit
        #: rester distincte d'une liste qui ne suivrait rien.
        self.categories = None if categories is None else tuple(categories)
        #: Les flux retirés du scoring et du résumé. Vides quand le document n'en déclare
        #: pas : tout article d'une catégorie suivie est alors noté, comme avant la clé.
        self.flux_exclus = flux_exclus if flux_exclus is not None else FluxExclus()


def load_profil(override: str | None = None) -> Profil:
    """Le document effectif : l'argument, sinon l'environnement, sinon le défaut.

    Priorité : `override` > `RSSRESUME_PROFILE` > `RSSRESUME_PROFILE_FILE` > défaut.
    Les deux variables ensemble sont une erreur de configuration ; le texte l'emporte,
    et ne porte alors que lui — ni stack, ni destinataire.

    Un fichier annoncé mais illisible lève une erreur au lieu de retomber sur le profil
    par défaut : noter toute une journée d'articles contre le mauvais critère de
    pertinence, sans rien dire, est le pire des deux comportements.
    """
    if override and override.strip():
        return Profil(override.strip())

    inline = (os.getenv(ENV_PROFIL) or "").strip()
    if inline:
        return Profil(inline)

    chemin = (os.getenv(ENV_PROFIL_FILE) or "").strip()
    if not chemin:
        return Profil(DEFAULT_PROFIL)
    return profil_depuis_fichier(pathlib.Path(chemin))


def profil_depuis_fichier(fichier: pathlib.Path) -> Profil:
    """Le profil d'un document sur le disque. Illisible, vide ou fautif : `ValueError`.

    Le même chemin pour le document unique de `RSSRESUME_PROFILE_FILE` et pour chaque
    fichier du dossier de profils : deux lectures qui divergeraient finiraient par
    accepter d'un côté ce que l'autre refuse.
    """
    fichier = pathlib.Path(fichier)
    try:
        contenu = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Profil illisible : {fichier} ({exc})") from exc
    if not contenu:
        raise ValueError(f"Profil vide : {fichier}")
    return _document(contenu, str(fichier))


def profil_depuis_dict(
    document: object,
    origine: str = "profil",
    catalogue: "Catalogue | None" = None,
    username: str = "",
) -> Profil:
    """Le profil porté par un objet JSON déjà décodé. Fautif : `ValueError`.

    Public parce que le site qui édite les profils valide un formulaire avant d'écrire
    le fichier : il doit refuser exactement ce que le passage du matin refuserait, et
    le seul moyen de le garantir est d'appeler la même fonction. `origine` ne sert qu'à
    situer l'erreur dans son message — un chemin, un nom de profil.

    Une stack fautive lève aussi `ValueError`, et non l'erreur propre à la stack :
    l'appelant n'a qu'une exception à attraper pour dire « ce document est refusé ».
    """
    if not isinstance(document, dict):
        raise ValueError(f"{origine} : un profil est un objet JSON, pas {type(document).__name__}.")

    texte = document.get(CLE_PROFIL)
    if not isinstance(texte, str) or not texte.strip():
        raise ValueError(f"{origine} : objet JSON sans texte à la clé « {CLE_PROFIL} ».")
    try:
        stack = Stack.declaree(document.get(CLE_STACK))
    except StackError as exc:
        raise ValueError(f"{origine} : {exc}") from exc
    try:
        axes = Axes.declares(document.get(CLE_AXES))
    except AxesError as exc:
        raise ValueError(f"{origine} : {exc}") from exc
    identifiant = document.get(CLE_ID)
    if identifiant is not None and not id_valide(identifiant):
        raise ValueError(
            f"{origine} : « {CLE_ID} » doit être un UUID sous sa forme canonique en "
            f"minuscules (par exemple {nouvel_id()}), pas « {identifiant} »."
        )
    categories = _categories(document.get(CLE_CATEGORIES), origine)
    if categories is not None and catalogue is not None:
        categories = catalogue.abonnement(categories, username, origine)
    return Profil(
        texte.strip(),
        stack,
        _emails(document.get(CLE_EMAIL), origine),
        _prenom(document.get(CLE_PRENOM), origine),
        identifiant or "",
        Securite.depuis_document(document.get(CLE_SECURITE), origine),
        axes,
        categories,
        FluxExclus.declares(document.get(CLE_FLUX_EXCLUS), origine),
    )


def nouvel_id() -> str:
    """Un identifiant de profil neuf : un UUID4, sous sa forme canonique en minuscules."""
    return str(uuid.uuid4())


def id_valide(valeur: object) -> bool:
    """Vrai pour un UUID écrit sous sa forme canonique, en minuscules.

    La forme est exigée, pas seulement le sens : l'identifiant nomme un répertoire, et
    deux écritures du même UUID — majuscules, accolades — en désigneraient deux.
    """
    if not isinstance(valeur, str):
        return False
    try:
        return str(uuid.UUID(valeur)) == valeur
    except ValueError:
        return False


def _document(contenu: str, origine: str) -> Profil:
    """Le profil porté par le fichier : un objet JSON, ou le texte tel quel.

    Le discriminant est l'accolade ouvrante, pas l'extension : celle-ci n'est qu'une
    promesse que rien ne vérifie, alors qu'un profil écrit en clair ne commence jamais
    par une accolade. Un fichier reconnu comme JSON et fautif lève donc, au lieu d'être
    servi comme du texte : le prompt de scoring recevrait sinon la ponctuation du
    fichier en guise de critère de pertinence, et la journée serait notée contre elle.
    """
    if not contenu.startswith("{"):
        return Profil(contenu)

    try:
        parsed = json.loads(contenu)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{origine} : JSON invalide : {exc}") from exc
    return profil_depuis_dict(parsed, origine)


def _prenom(valeur: object, origine: str) -> str:
    """Le prénom déclaré, s'il l'est. Absent, la salutation se passe de nom.

    Facultatif, mais pas permissif : une clé remplie avec autre chose qu'un texte lève au
    lancement. Sans cela, la seule façon de s'en apercevoir serait d'entendre la
    salutation se tromper un matin — et l'audio est justement ce qu'on ne relit pas.
    """
    if valeur is None:
        return ""
    if not isinstance(valeur, str):
        raise ValueError(
            f"{origine} : la clé « {CLE_PRENOM} » attend un prénom écrit en "
            f"toutes lettres, pas {type(valeur).__name__}."
        )
    return valeur.strip()


def _categories(valeur: object, origine: str) -> tuple[str, ...] | None:
    """Les libellés suivis, rognés ; `None` si la clé manque. Mal formés : `ValueError`.

    La liste vide est refusée : un digest qui ne suit rien n'est pas un choix qu'on fait
    exprès, et l'accepter la confondrait avec l'absence, qui veut dire « tout ». Un doublon
    — casse et accents retirés, comme le catalogue compare — l'est aussi : il dirait deux
    fois la même chose, et le second masquerait une faute de recopie.
    """
    if valeur is None:
        return None
    if not isinstance(valeur, list) or not valeur:
        raise ValueError(
            f"{origine} : « {CLE_CATEGORIES} » est une liste non vide de libellés de "
            "catégorie. Retirer la clé pour recevoir tout ce que le catalogue autorise."
        )
    vues: dict[str, str] = {}
    for libelle in valeur:
        if not isinstance(libelle, str) or not libelle.strip():
            raise ValueError(
                f"{origine} : « {CLE_CATEGORIES} » ne contient que des libellés non vides, "
                f"pas « {libelle} »."
            )
        cle = casefold_ascii(libelle.strip())
        if cle in vues:
            raise ValueError(
                f"{origine} : « {CLE_CATEGORIES} » nomme deux fois la même catégorie "
                f"(« {vues[cle]} » et « {libelle.strip()} »)."
            )
        vues[cle] = libelle.strip()
    return tuple(vues.values())


def _emails(valeur: object, origine: str) -> tuple[str, ...]:
    """Le ou les destinataires déclarés : une adresse, ou une liste d'adresses.

    Une adresse est vérifiée à l'arobase, et pas davantage : le reste ne se saurait qu'au
    refus du serveur, le soir venu. Ce peu-là suffit à attraper la faute qui arrive
    vraiment — une clé remplie avec autre chose qu'une adresse — au lancement, quand on
    la lit encore.
    """
    if valeur is None:
        return ()
    adresses = [valeur] if isinstance(valeur, str) else valeur
    if not isinstance(adresses, list) or not adresses:
        raise ValueError(
            f"{origine} : « {CLE_EMAIL} » est une adresse, ou une liste d'adresses."
        )
    for adresse in adresses:
        if not isinstance(adresse, str) or "@" not in adresse:
            raise ValueError(f"{origine} : « {adresse} » n'est pas une adresse email.")
    return tuple(adresse.strip() for adresse in adresses)


def username_valide(username: object) -> bool:
    """Vrai quand `username` peut nommer un profil : répertoire, préfixe de tags, fichier."""
    return isinstance(username, str) and MOTIF_USERNAME.match(username) is not None


def valider_username(username: object) -> str:
    """Le nom tel quel s'il est valide ; sinon `ValueError`, qui dit la règle.

    Pas de normalisation (minuscules, espaces retirés) : un nom corrigé en silence
    désignerait un autre répertoire et d'autres tags que ceux que la personne croit.
    """
    if not username_valide(username):
        raise ValueError(
            f"Nom de profil invalide : « {username} ». Attendu : 2 à 32 caractères, "
            "minuscules, chiffres, « - » ou « _ », commençant par une lettre ou un chiffre."
        )
    return username


class Lecteur:
    """Une personne du digest : son nom, et le profil qu'elle a déclaré.

    Le nom est à part du `Profil` parce qu'il n'est pas dans le document : il est celui
    du fichier. Un profil passé en ligne (`RSSRESUME_PROFILE`) n'en a pas, une personne
    servie par la tournée en a toujours un.
    """

    def __init__(self, username: str, profil: Profil):
        self.username = valider_username(username)
        if not id_valide(profil.id):
            raise ValueError(f"Profil « {username} » sans identifiant valide (« {CLE_ID} »).")
        self.profil = profil

    @property
    def id(self) -> str:
        return self.profil.id


class Annuaire:
    """Les personnes que le passage quotidien sert, et comment lire chacune.

    La base porte ce qui ne dépend pas de l'endroit où vivent les documents — lister,
    cibler un nom, charger tout le monde ; les sous-classes ne disent que la source.
    Les noms et les profils sont lus séparément, et à la demande : un document fautif
    ne doit coûter que la journée de sa personne, pas celle des autres, et se signaler
    au moment où on la sert.
    """

    def usernames(self) -> list[str]:
        """Les noms servis, triés : l'ordre de la tournée ne doit pas dépendre du disque."""
        raise NotImplementedError

    def profil(self, username: str) -> Profil:
        """Le profil d'un nom déjà listé. Fautif : `ValueError`."""
        raise NotImplementedError

    def catalogue(self) -> Catalogue:
        """Le catalogue des catégories (`categories.Catalogue`) : ouvert, sauf en base.

        Seule la base sait le porter — un dossier de profils n'a pas d'endroit commun où
        le ranger. Ouvert, il sert tout à tout le monde, et la tournée ne l'accepte que
        pour une seule personne. Import différé : `categories` dépend de ce module.
        """
        from rssresume.categories import CatalogueOuvert

        return CatalogueOuvert()

    def remede_sans_catalogue(self) -> str:
        """Ce qu'il faut faire pour avoir un catalogue, depuis cette source de profils.

        Hors de la base, il n'y a nulle part où le ranger : le seul remède est d'y passer,
        et le message doit le dire plutôt que de proposer une commande qui exige la base.
        """
        return (
            f"Hors de la base, aucun catalogue n'est possible : passer à la base des profils "
            f"({ENV_PROFILES_DB}, puis python -m rssresume.api importer <dossier>, et retirer "
            f"{ENV_PROFILES_DIR} / {ENV_PROFIL_FILE}), puis importer le catalogue "
            "(python -m rssresume.api importer-catalogue <fichier.json>, voir "
            "docs/categories.exemple.json)."
        )

    def lecteur(self, username: str) -> Lecteur:
        """La personne `username`, profil chargé. Inconnue ou fautive : `ValueError`.

        Un identifiant porté par un autre profil lève aussi, des deux côtés : les deux
        écriraient dans le même répertoire, et ni l'un ni l'autre n'est servi plutôt que
        de mélanger leurs journées.
        """
        self._connu(username)
        profil = self.profil(username)
        doublons = [
            autre for autre in self.usernames() if autre != username and self._id_de(autre) == profil.id
        ]
        if doublons:
            raise ValueError(
                f"Profil « {username} » : l'identifiant {profil.id} est aussi celui de "
                f"{', '.join(doublons)}. Aucun n'est servi tant qu'un des documents n'a pas "
                f"un autre « {CLE_ID} »."
            )
        return Lecteur(username, profil)

    def _id_de(self, username: str) -> str | None:
        """L'identifiant d'un autre profil, `None` s'il est illisible — signalé à son tour."""
        try:
            return self.profil(username).id
        except ValueError:
            return None

    @staticmethod
    def _lire_document(fichier: pathlib.Path) -> Profil:
        """Le profil d'un document, avec son identifiant — généré et écrit s'il manque.

        Le document doit être un objet JSON : un texte brut n'a pas de place où ranger
        l'identifiant, et sans lui la personne n'a pas de répertoire de sortie.

        L'identifiant manquant est écrit dans le fichier même, clés existantes
        conservées : généré à chaque passage, il changerait chaque matin, et la
        personne retrouverait chaque matin un répertoire vide.
        """
        try:
            contenu = fichier.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"Profil illisible : {fichier} ({exc})") from exc
        if not contenu.startswith("{"):
            raise ValueError(
                f"{fichier} : un profil est un objet JSON, pas du texte brut — il doit pouvoir "
                f'porter son « {CLE_ID} ». Le convertir en {{"{CLE_PROFIL}": "…"}}.'
            )
        try:
            document = json.loads(contenu)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{fichier} : JSON invalide : {exc}") from exc
        profil = profil_depuis_dict(document, str(fichier))
        if not profil.id:
            profil.id = nouvel_id()
            complet = {CLE_ID: profil.id, **document}
            fichier.write_text(json.dumps(complet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            console.log(f"Profil {fichier} : identifiant {profil.id} généré et écrit dans le document")
        return profil

    def cibles(self, username: str | None = None) -> list[str]:
        """Les noms à servir : tous, ou celui demandé — qui doit exister.

        Un nom inconnu lève avant tout traitement : une faute de frappe dans `--profil`
        ne doit ni tourner à vide ni servir tout le monde à la place.
        """
        if username is None:
            return self.usernames()
        self._connu(username)
        return [username]

    def _connu(self, username: str) -> None:
        connus = self.usernames()
        if username not in connus:
            raise ValueError(
                f"Profil inconnu : « {username} ». Profils disponibles : "
                f"{', '.join(connus) or '(aucun)'}."
            )

    @classmethod
    def depuis_env(cls) -> "Annuaire":
        """L'annuaire que l'environnement décrit. Ambigu : `ValueError`, au lancement.

        - `RSSRESUME_PROFILES_DB` : un profil par ligne de la base, exclusive de tout le
          reste (`_annuaire_sqlite`) ;
        - `RSSRESUME_PROFILES_DIR` : un profil par fichier du dossier ;
        - sinon `RSSRESUME_PROFILE_FILE` : ce document est l'unique profil, nommé
          d'après son fichier (`input/adrien.json` → `adrien`) ;
        - sinon personne : la tournée ne lit rien et ne résume rien.

        Le dossier **et** une des variables à profil unique sont refusés ensemble :
        servir l'un en ignorant l'autre ferait disparaître une personne — ou en ferait
        apparaître une — sans que rien ne le dise. C'est l'état transitoire d'une
        migration, et il doit se voir au déploiement.

        `RSSRESUME_PROFILE` n'est plus servie par la tournée : un profil sans nom n'a ni
        répertoire ni préfixe de tags. Posée, elle lève plutôt que d'être ignorée — sans
        quoi une installation qui en dépendait cesserait d'envoyer son digest sans un mot.
        """
        base = (os.getenv(ENV_PROFILES_DB) or "").strip()
        if base:
            return _annuaire_sqlite(base)
        dossier = (os.getenv(ENV_PROFILES_DIR) or "").strip()
        fichier = (os.getenv(ENV_PROFIL_FILE) or "").strip()
        if dossier:
            uniques = [nom for nom in (ENV_PROFIL_FILE, ENV_PROFIL) if (os.getenv(nom) or "").strip()]
            if uniques:
                raise ValueError(
                    f"{ENV_PROFILES_DIR} et {' / '.join(uniques)} sont posées ensemble. "
                    f"Avec un dossier de profils, déplacer le document dans "
                    f"{dossier}/<username>.json et retirer {' / '.join(uniques)} de "
                    "l'environnement."
                )
            return AnnuaireDossier(pathlib.Path(dossier))
        if (os.getenv(ENV_PROFIL) or "").strip():
            raise ValueError(
                f"{ENV_PROFIL} n'est plus lue : un profil se déclare dans un document "
                f'{{"{CLE_PROFIL}": "…"}}, nommé <username>{EXTENSION_PROFIL}, désigné par '
                f"{ENV_PROFIL_FILE} ou déposé dans {ENV_PROFILES_DIR}. Retirer {ENV_PROFIL} "
                "de l'environnement."
            )
        if fichier:
            return AnnuaireFichier(pathlib.Path(fichier))
        return AnnuaireVide()


def _annuaire_sqlite(base: str) -> Annuaire:
    """La base de profils, seule source déclarée. Combinée à une autre : `ValueError`.

    Même arbitrage que le dossier : pendant la migration, le dossier et la base coexistent
    sur le disque, et servir l'un en ignorant l'autre ferait apparaître ou disparaître des
    personnes sans un mot. Import différé : `annuaire_sqlite` dépend de ce module.
    """
    autres = [
        nom
        for nom in (ENV_PROFILES_DIR, ENV_PROFIL_FILE, ENV_PROFIL)
        if (os.getenv(nom) or "").strip()
    ]
    if autres:
        raise ValueError(
            f"{ENV_PROFILES_DB} et {' / '.join(autres)} sont posées ensemble. Avec une base "
            f"de profils, importer les documents (python -m rssresume.api importer <chemin>) "
            f"puis retirer {' / '.join(autres)} de l'environnement."
        )
    from rssresume.annuaire_sqlite import AnnuaireSqlite

    return AnnuaireSqlite(pathlib.Path(base))


class AnnuaireDossier(Annuaire):
    """Un dossier de documents, un `{username}.json` par personne.

    Relu à chaque appel, sans cache : le site peut ajouter ou modifier un profil entre
    deux passages, et le passage du matin doit servir l'état du matin.
    """

    def __init__(self, dossier: pathlib.Path):
        self.dossier = pathlib.Path(dossier)
        #: Les fichiers mal nommés déjà signalés : la liste est relue plusieurs fois par
        #: tournée, l'erreur n'a à s'écrire qu'une fois.
        self._signales: set[str] = set()

    def chemin(self, username: str) -> pathlib.Path:
        """Où vit — ou vivra — le document de `username`. Le nom est validé d'abord."""
        return self.dossier / f"{valider_username(username)}{EXTENSION_PROFIL}"

    def usernames(self) -> list[str]:
        """Les noms du dossier. Un fichier `.json` au nom invalide est signalé et sauté.

        Sauté et non levé : un fichier mal nommé ne doit pas coûter la journée de toutes
        les autres personnes. Signalé et non ignoré : sans un mot, il ferait disparaître
        quelqu'un de la tournée.
        """
        if not self.dossier.is_dir():
            raise ValueError(
                f"{ENV_PROFILES_DIR} : le dossier {self.dossier} n'existe pas. Le créer et "
                f"y déposer un <username>{EXTENSION_PROFIL} par personne."
            )
        noms = sorted(
            fichier.stem
            for fichier in self.dossier.iterdir()
            if fichier.is_file() and fichier.suffix == EXTENSION_PROFIL
        )
        for nom in noms:
            if not username_valide(nom) and nom not in self._signales:
                self._signales.add(nom)
                console.error(
                    f"{ENV_PROFILES_DIR} : {self.dossier / (nom + EXTENSION_PROFIL)} ignoré, "
                    f"« {nom} » n'est pas un nom de profil. Attendu : 2 à 32 caractères, "
                    "minuscules, chiffres, « - » ou « _ », commençant par une lettre ou un "
                    "chiffre. Renommer le fichier."
                )
        return [nom for nom in noms if username_valide(nom)]

    def profil(self, username: str) -> Profil:
        return self._lire_document(self.chemin(username))


class AnnuaireFichier(Annuaire):
    """L'installation à une seule personne : le document de `RSSRESUME_PROFILE_FILE`.

    Son nom est celui du fichier, pour que passer ensuite au dossier de profils ne soit
    qu'un déplacement : `input/adrien.json` tague déjà `adrien-…`, et son `id` — écrit
    dans le fichier — le suit dans le dossier avec ses journées.
    """

    def __init__(self, fichier: pathlib.Path):
        self.fichier = pathlib.Path(fichier)
        if not username_valide(self.fichier.stem):
            raise ValueError(
                f"{ENV_PROFIL_FILE} : le nom du fichier ({self.fichier.name}) devient le nom "
                f"du profil, et « {self.fichier.stem} » n'en est pas un valide "
                f"({MOTIF_USERNAME.pattern}). Renommer le fichier."
            )

    def usernames(self) -> list[str]:
        return [self.fichier.stem]

    def profil(self, username: str) -> Profil:
        return self._lire_document(self.fichier)


class AnnuaireVide(Annuaire):
    """Aucun document déclaré : personne à servir.

    Plus de profil générique servi par défaut : un digest noté contre un critère que
    personne n'a écrit, envoyé à personne, ne coûtait que des appels.
    """

    def usernames(self) -> list[str]:
        return []

    def profil(self, username: str) -> Profil:
        raise ValueError(f"Profil inconnu : « {username} ». Aucun profil n'est déclaré.")


def lister_profils(dossier: pathlib.Path) -> list[str]:
    """Les `username` d'un dossier de profils. Raccourci public pour le site."""
    return AnnuaireDossier(dossier).usernames()


def charger_profil(dossier: pathlib.Path, username: str) -> Profil:
    """Le profil de `username` dans un dossier de profils, identifiant compris.

    Un document sans identifiant en reçoit un, écrit dans le fichier.
    """
    return AnnuaireDossier(dossier).profil(username)
