"""Les avis CERT-FR, triés sans le moindre appel à un modèle.

La catégorie des avis de l'ANSSI ne ressemble à aucune autre du digest : cinq à dix
articles par jour, tous bâtis sur le même moule, dont la réponse utile tient en une
ligne — est-ce que ça touche ma stack. Le pipeline LLM y était à contre-emploi : cher,
répétitif, et illisible à l'oreille.

    from rssresume import certfr

    certfr.CertfrService().lire(articles).phrase

Une catégorie y est routée par `RSSRESUME_CERTFR_CATEGORIES` (voir `config.py`), ce qui
lui fait sauter le scoring, le résumé et la synthèse vocale d'un bloc.

Le paquet sépare les données du procédé, comme `ephemeride/` :

- `stack` : ce qu'est un composant surveillé, et l'appariement ;
- `service` : la lecture d'une journée, le classement par impact, et la phrase produite.

Ce module ne réexporte que la façade. Ajouter un composant se fait dans le document de
profil, hors du dépôt, et n'oblige à relire ni l'un ni l'autre.
"""

from rssresume.certfr import service, stack
from rssresume.certfr.service import (
    ECHELLE,
    INDETERMINEE,
    Avis,
    CertfrService,
    Criticite,
    Revue,
    criticite_de,
)
from rssresume.certfr.stack import CLE_STACK, Composant, Stack, StackError

__all__ = [
    "CLE_STACK",
    "ECHELLE",
    "INDETERMINEE",
    "Avis",
    "CertfrService",
    "Composant",
    "Criticite",
    "Revue",
    "Stack",
    "StackError",
    "criticite_de",
    "service",
    "stack",
]
