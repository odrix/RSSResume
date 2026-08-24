"""Profil de pertinence : la définition de ce qui, pour cet auditeur, est une information.

Ce texte est le seul élément vraiment personnel du système. Il est utilisé par les
trois prompts — noter, résumer un article, dicter le digest audio — et c'est lui qui
décide de tout le reste : ce qui monte au-dessus du seuil, ce qui est raconté, et sous
quel angle. Ouvrir l'outil à quelqu'un d'autre, c'est changer ce texte et rien d'autre.

Il est donc chargé, pas codé en dur au point d'appel : un profil explicite passé en
argument, sinon l'environnement, sinon le profil par défaut ci-dessous.
"""

from __future__ import annotations

import os
import pathlib

#: Le texte lui-même, pour un profil court.
ENV_PROFIL = "RSSRESUME_PROFILE"
#: Le chemin d'un fichier, pour un profil long ou versionné à part.
ENV_PROFIL_FILE = "RSSRESUME_PROFILE_FILE"

DEFAULT_PROFIL = """CTO d'un SaaS B2B français de stockage, partage et transfert de fichiers
sécurisé. Infrastructure hébergée en France, qualifiée SecNumCloud, produit certifié
CSPN par l'ANSSI.

Axes de veille pertinents :
- reglementaire : souveraineté et conformité (SecNumCloud, EUCS, NIS2, DORA, RGPD,
  doctrine ANSSI, Cloud Act / FISA, décisions CNIL).
- cyber : cybersécurité technique (CVE exploitables, chiffrement, gestion de clés,
  crypto post-quantique, chaîne d'approvisionnement logicielle, incidents majeurs).
- marche : marché et concurrence (acteurs du transfert de fichiers sécurisé et du
  cloud souverain français ou européen, levées, rachats, appels d'offres publics).
- stack : veille technologique sur la stack d'un SaaS de ce type (stockage objet,
  chiffrement de bout en bout, performance de transfert, observabilité, coûts cloud).

Ne sont PAS pertinents : l'actualité IA grand public, les levées de fonds hors de ce
marché, le hardware grand public, les annonces produit sans impact technique ou
réglementaire pour cet éditeur."""


def load_profil(override: str | None = None) -> str:
    """Profil effectif : l'argument, sinon l'environnement, sinon le profil par défaut.

    Priorité : `override` > `RSSRESUME_PROFILE` > `RSSRESUME_PROFILE_FILE` > défaut.
    Les deux variables ensemble sont une erreur de configuration ; le texte l'emporte.

    Un fichier annoncé mais illisible lève une erreur au lieu de retomber sur le profil
    par défaut : noter toute une journée d'articles contre le mauvais critère de
    pertinence, sans rien dire, est le pire des deux comportements.
    """
    if override and override.strip():
        return override.strip()

    inline = (os.getenv(ENV_PROFIL) or "").strip()
    if inline:
        return inline

    chemin = (os.getenv(ENV_PROFIL_FILE) or "").strip()
    if not chemin:
        return DEFAULT_PROFIL

    fichier = pathlib.Path(chemin)
    try:
        contenu = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"{ENV_PROFIL_FILE} désigne un fichier illisible : {fichier} ({exc})") from exc
    if not contenu:
        raise ValueError(f"{ENV_PROFIL_FILE} désigne un fichier vide : {fichier}")
    return contenu
