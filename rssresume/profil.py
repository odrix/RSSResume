"""Le document d'une personne : son profil de pertinence, sa stack, son destinataire.

Le profil de pertinence est le seul élément vraiment personnel du système. Il est
utilisé par les trois prompts — noter, résumer un article, dicter le digest audio — et
c'est lui qui décide de tout le reste : ce qui monte au-dessus du seuil, ce qui est
raconté, et sous quel angle. Ouvrir l'outil à quelqu'un d'autre, c'est changer ce texte
et rien d'autre.

Les deux autres sont personnelles pour la même raison, et se lisent au même endroit :
ce qu'on exploite (la liste de composants sur laquelle les avis CERT-FR sont appariés)
et à qui le digest est envoyé. Trois fichiers et trois variables d'environnement pour un
seul lecteur n'avaient d'autre effet que de multiplier les chemins à tenir — un seul
document, hors du dépôt, en dit autant :

    {"profil": "CTO d'un SaaS…", "stack": ["Traefik"], "email": "moi@example.com"}

Il est donc chargé, pas codé en dur au point d'appel : un profil explicite passé en
argument, sinon l'environnement, sinon le profil par défaut ci-dessous. Ce défaut ne
décrit personne : il vaut pour quelqu'un dans la tech, sans dire de quel produit ni de
quelle équipe.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Iterable

from rssresume.certfr.stack import CLE_STACK, Stack

#: Le texte du profil seul, pour un profil court. Ne porte ni stack ni destinataire :
#: une valeur d'environnement est une ligne, pas un document.
ENV_PROFIL = "RSSRESUME_PROFILE"
#: Le chemin du document, c'est-à-dire le cas normal hors du dépôt.
ENV_PROFIL_FILE = "RSSRESUME_PROFILE_FILE"

#: Les clés du document. `profil` est la seule exigée.
CLE_PROFIL = "profil"
CLE_EMAIL = "email"
#: Le prénom, pour la salutation de l'audio de journée. Il est ici et pas ailleurs pour
#: la même raison que l'adresse : comment on s'adresse à quelqu'un est aussi personnel
#: que ce qu'il veut lire, et rien de personnel ne se déclare dans l'environnement.
CLE_PRENOM = "prenom"

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
    ):
        self.texte = texte
        #: Vide quand le document ne déclare rien : aucun avis n'est alors apparié, et
        #: la phrase du digest le dit plutôt que d'annoncer que rien ne nous concerne.
        self.stack = stack if stack is not None else Stack()
        #: Les destinataires du digest. Vides, aucun email ne part — c'est déjà ce que
        #: faisait `SMTP_TO` absente.
        self.emails = tuple(emails)
        #: Le prénom qui ouvre l'audio de journée. Vide, le montage n'appelle personne
        #: par son nom : c'est une salutation en moins, pas une erreur.
        self.prenom = prenom


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

    fichier = pathlib.Path(chemin)
    try:
        contenu = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"{ENV_PROFIL_FILE} désigne un fichier illisible : {fichier} ({exc})") from exc
    if not contenu:
        raise ValueError(f"{ENV_PROFIL_FILE} désigne un fichier vide : {fichier}")
    return _document(contenu, fichier)


def _document(contenu: str, fichier: pathlib.Path) -> Profil:
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
        raise ValueError(f"{ENV_PROFIL_FILE} : JSON invalide ({fichier}) : {exc}") from exc

    texte = parsed.get(CLE_PROFIL)
    if not isinstance(texte, str) or not texte.strip():
        raise ValueError(
            f"{ENV_PROFIL_FILE} : objet JSON sans texte à la clé « {CLE_PROFIL} » "
            f"({fichier})."
        )
    return Profil(
        texte.strip(),
        Stack.declaree(parsed.get(CLE_STACK)),
        _emails(parsed.get(CLE_EMAIL), fichier),
        _prenom(parsed.get(CLE_PRENOM), fichier),
    )


def _prenom(valeur: object, fichier: pathlib.Path) -> str:
    """Le prénom déclaré, s'il l'est. Absent, la salutation se passe de nom.

    Facultatif, mais pas permissif : une clé remplie avec autre chose qu'un texte lève au
    lancement. Sans cela, la seule façon de s'en apercevoir serait d'entendre la
    salutation se tromper un matin — et l'audio est justement ce qu'on ne relit pas.
    """
    if valeur is None:
        return ""
    if not isinstance(valeur, str):
        raise ValueError(
            f"{ENV_PROFIL_FILE} : la clé « {CLE_PRENOM} » attend un prénom écrit en "
            f"toutes lettres, pas {type(valeur).__name__} ({fichier})."
        )
    return valeur.strip()


def _emails(valeur: object, fichier: pathlib.Path) -> tuple[str, ...]:
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
            f"{ENV_PROFIL_FILE} : « {CLE_EMAIL} » est une adresse, ou une liste "
            f"d'adresses ({fichier})."
        )
    for adresse in adresses:
        if not isinstance(adresse, str) or "@" not in adresse:
            raise ValueError(
                f"{ENV_PROFIL_FILE} : « {adresse} » n'est pas une adresse email "
                f"({fichier})."
            )
    return tuple(adresse.strip() for adresse in adresses)
