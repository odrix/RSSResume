"""Les composants surveillés, et la façon de les repérer dans un texte.

La liste, elle, vient du document de la personne — `profil.py`, clé `stack` — et pas
d'ici : ce qu'on exploite se tient hors du dépôt, avec le profil de pertinence et le
destinataire du digest. Ce module ne porte que le procédé, qui ne bouge presque jamais
là où la liste se corrige à chaque changement d'infrastructure. C'est le même découpage
que `ephemeride/`, pour la même raison.

    Stack.declaree(["Keycloak"]).concernes("Multiples vulnérabilités dans Keycloak")
    -> ("Keycloak",)

L'appariement est volontairement pauvre : une suite de mots contigus, casse et accents
retirés. Rien de flou, rien d'approché. Un avis de sécurité mal apparié est pire qu'un
avis manqué — il fait ouvrir un ticket sur un composant qu'on n'exploite pas, et la fois
suivante on ne lit plus la phrase.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from rssresume.tools.text import contains_words, words

#: La clé qui porte la liste dans le document de profil.
CLE_STACK = "stack"


class StackError(RuntimeError):
    """Liste de composants dont une entrée n'a pas la bonne forme."""


class Composant:
    """Un composant de la stack : son nom canonique, et les écritures qui le désignent.

    Le nom canonique est celui qui sera écrit dans la phrase du digest ; les alias ne
    servent qu'à reconnaître. Les deux sont gardés tels qu'ils ont été déclarés — c'est
    sur eux que porte l'empreinte du journal — et découpés une fois à la construction :
    l'appariement tourne sur chaque avis de chaque matin, il n'a pas à redécouper.
    """

    def __init__(self, nom: str, alias: Iterable[str] = ()):
        self.nom = nom
        self.alias = tuple(alias)
        #: Chaque écriture réduite à sa suite de mots. Celles qui ne portent ni lettre
        #: ni chiffre sont écartées : elles reconnaîtraient n'importe quel texte.
        self._formes = tuple(
            forme for forme in (words(ecriture) for ecriture in (nom, *self.alias)) if forme
        )

    @property
    def reconnaissable(self) -> bool:
        """Faux pour un composant dont aucune écriture ne porte de mot appariable."""
        return bool(self._formes)

    def figure_dans(self, mots: tuple[str, ...]) -> bool:
        return any(contains_words(mots, forme) for forme in self._formes)


class Stack:
    """Les composants surveillés, et ce qu'un texte d'avis en touche.

    Objet et non liste nue : c'est lui qui sait apparier, et c'est lui que le journal
    interroge pour dire contre quelle liste la journée a été lue.
    """

    def __init__(self, composants: Iterable[Composant] = ()):
        self._composants = tuple(composants)

    @classmethod
    def declaree(cls, entrees: object) -> "Stack":
        """La stack telle que le document de profil la déclare, sous la clé `stack`.

        Une entrée est une **chaîne** — le nom canonique, sans alias, le cas courant —
        ou un **objet** `{"nom": …, "alias": […]}` quand les avis emploient plusieurs
        écritures. Absente, la clé donne une stack vide : c'est l'état de départ de
        quiconque installe l'outil, et le digest le dit en toutes lettres.

        Une entrée fautive lève au lieu d'être sautée. Un composant sauté ne se remarque
        pas : la journée se déroule, la phrase se rédige, et il manque simplement le seul
        avis qu'on attendait.
        """
        if entrees is None:
            return cls()
        if not isinstance(entrees, list):
            raise StackError(
                f"« {CLE_STACK} » : liste attendue, de la forme "
                '["Traefik", {"nom": "Keycloak", "alias": ["RH-SSO"]}].'
            )
        return cls(_composant(entree) for entree in entrees)

    def __len__(self) -> int:
        return len(self._composants)

    @property
    def vide(self) -> bool:
        """Vrai tant que personne n'a déclaré de composant.

        Le cas mérite d'être nommé : une stack vide n'apparie rien, et le digest doit
        le dire au lieu d'annoncer sereinement que la journée ne nous concerne pas.
        """
        return not self._composants

    @property
    def empreinte(self) -> str:
        """Empreinte courte de la liste déclarée, nom et alias compris.

        Le pendant de `empreinte_scoring` pour une catégorie déterministe : deux
        journaux dont elle diffère n'ont pas été appariés contre la même stack, et une
        journée qui ne signalait rien s'explique alors sans avoir à retrouver le fichier
        de l'époque. Elle porte sur ce qui est déclaré, non sur la façon de l'écrire :
        « Traefik » et `{"nom": "Traefik"}` sont la même stack.
        """
        graine = json.dumps(
            {composant.nom: list(composant.alias) for composant in self._composants},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(graine.encode("utf-8")).hexdigest()[:12]

    def concernes(self, texte: str) -> tuple[str, ...]:
        """Les noms canoniques des composants que ce texte cite, dans l'ordre déclaré."""
        vus = words(texte)
        return tuple(
            composant.nom for composant in self._composants if composant.figure_dans(vus)
        )


def _composant(entree: object) -> Composant:
    """Une entrée de la liste relue en objet, sa forme étant exigée."""
    if isinstance(entree, str):
        composant = Composant(entree)
    elif isinstance(entree, dict):
        nom = entree.get("nom")
        if not isinstance(nom, str) or not nom.strip():
            raise StackError(
                f"« {CLE_STACK} » : une entrée sans « nom » — la clé porte le nom "
                "canonique, celui qui sera écrit dans la phrase du digest."
            )
        alias = entree.get("alias") or []
        if not isinstance(alias, list) or any(not isinstance(item, str) for item in alias):
            raise StackError(f"Composant « {nom} » : « alias » doit être une liste de chaînes.")
        composant = Composant(nom, alias)
    else:
        raise StackError(
            f"« {CLE_STACK} » : une entrée est une chaîne — « Traefik » — ou un objet "
            '{"nom": "Keycloak", "alias": ["RH-SSO"]}.'
        )

    if not composant.reconnaissable:
        raise StackError(
            f"Composant « {composant.nom} » : ni le nom ni les alias ne portent de lettre "
            "ou de chiffre, rien ne pourrait l'apparier."
        )
    return composant
