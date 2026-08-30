"""La liste des composants surveillés, et la façon de les repérer dans un texte.

Les données sont dans `stack.json`, le procédé ici : la liste se corrige à chaque
changement d'infrastructure, la façon de l'apparier ne bouge presque jamais. C'est le
même découpage que `ephemeride/`, pour la même raison.

    charger().concernes("Multiples vulnérabilités dans Keycloak")  -> ("Keycloak",)

L'appariement est volontairement pauvre : une suite de mots contigus, casse et accents
retirés. Rien de flou, rien d'approché. Un avis de sécurité mal apparié est pire qu'un
avis manqué — il fait ouvrir un ticket sur un composant qu'on n'exploite pas, et la fois
suivante on ne lit plus la phrase.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
import pathlib
from typing import Iterable

from rssresume.tools.text import contains_words, words

#: Fichier externe fusionné par-dessus celui qui est livré, pour tenir la vraie liste
#: hors du dépôt. Annoncé mais illisible, il fait échouer le lancement.
ENV_STACK_FILE = "RSSRESUME_STACK_FILE"

BUILTIN_PATH = pathlib.Path(__file__).with_name("stack.json")


class StackError(RuntimeError):
    """Liste de composants illisible, vide, ou dont une entrée n'a pas la bonne forme."""


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

    def __len__(self) -> int:
        return len(self._composants)

    @property
    def vide(self) -> bool:
        """Vrai tant que personne n'a rempli `stack.json`.

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
        de l'époque.
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


def charger() -> Stack:
    """La stack surveillée : le fichier livré, complété par `RSSRESUME_STACK_FILE`."""
    return _stack((os.getenv(ENV_STACK_FILE) or "").strip() or None)


@functools.lru_cache(maxsize=8)
def _stack(external: str | None) -> Stack:
    """Stack construite une fois par chemin externe : elle ne bouge pas en cours d'exécution."""
    table = _lire(BUILTIN_PATH, "Liste de composants livrée")
    if external:
        table = _fusionner(table, _lire(pathlib.Path(external), ENV_STACK_FILE))
    return Stack(_composants(table))


def _lire(path: pathlib.Path, annonce: str) -> dict:
    """Le contenu utile d'un fichier de composants. Illisible ou vide : on lève.

    Retomber en silence sur la liste livrée ferait apparier une journée entière d'avis
    contre une stack qui n'est pas celle qu'on croit, et le digest conclurait tranquillement
    que rien ne nous touche. Même arbitrage que le fichier de profil.
    """
    try:
        contenu = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise StackError(f"{annonce} : fichier illisible ({path}) : {exc}") from exc
    if not contenu:
        raise StackError(f"{annonce} : fichier vide ({path})")
    try:
        parsed = json.loads(contenu)
    except json.JSONDecodeError as exc:
        raise StackError(f"{annonce} : JSON invalide ({path}) : {exc}") from exc
    if not isinstance(parsed, dict):
        raise StackError(f"{annonce} : objet JSON attendu ({path})")
    # Les clés qui commencent par `_` sont des commentaires et des exemples, pas des
    # composants : c'est ce qui permet au fichier livré de se documenter lui-même.
    return {nom: bloc for nom, bloc in parsed.items() if not str(nom).startswith("_")}


def _fusionner(base: dict, overlay: dict) -> dict:
    """Fusion en profondeur : un fichier externe ne redéclare que ce qu'il change."""
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _fusionner(merged[key], value)
        else:
            merged[key] = value
    return merged


def _composants(table: dict) -> list[Composant]:
    """Les entrées relues en objets, une forme fautive levant plutôt que d'être sautée.

    Un composant sauté ne se remarque pas : la journée se déroule, la phrase se rédige,
    et il manque simplement le seul avis qu'on attendait. La forme est donc exigée.
    """
    composants = []
    for nom, bloc in table.items():
        if not isinstance(bloc, dict):
            raise StackError(
                f"Composant « {nom} » : objet attendu, de la forme "
                '{"alias": ["autre ecriture"]}.'
            )
        alias = bloc.get("alias") or []
        if not isinstance(alias, list) or any(not isinstance(item, str) for item in alias):
            raise StackError(f"Composant « {nom} » : « alias » doit être une liste de chaînes.")
        composant = Composant(str(nom), alias)
        if not composant.reconnaissable:
            raise StackError(
                f"Composant « {nom} » : ni le nom ni les alias ne portent de lettre ou de "
                "chiffre, rien ne pourrait l'apparier."
            )
        composants.append(composant)
    return composants
