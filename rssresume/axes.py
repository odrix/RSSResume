"""Les axes de veille : les rubriques entre lesquelles le scoring range un article.

Les cinq thématiques d'origine — reglementaire, cyber, marche, stack, autre — sont la
taxonomie d'un directeur technique d'éditeur. Pour un QA, un PO ou un designer, tout
tombait dans `autre`, et le regroupement à l'écoute ne voulait plus rien dire. La
personne déclare donc les siennes, dans son document (`profil.py`, clé `axes`) :

    {"axes": [{"slug": "tests", "libelle": "Tests", "description": "outillage, méthodes"}, …]}

Le procédé reste ici, la liste là-bas — le découpage de `certfr/stack.py`. Sans la clé,
ce sont les cinq d'origine, et le prompt comme son empreinte restent ceux d'avant à
l'octet près : un profil existant n'est pas renoté pour une clé qu'il ne porte pas.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Iterable, Iterator

from rssresume.models import THEMATIQUES

#: La clé qui porte les axes dans le document de profil.
CLE_AXES = "axes"
#: Un slug devient un label FreshRSS (`theme-<slug>`), relu par `Etiquettes` : minuscules,
#: chiffres et tirets, comme un nom de profil, et court, parce qu'il s'affiche dans la
#: colonne étroite du marqueur `.no-article` et dans la liste des labels.
MOTIF_SLUG = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
#: En dessous de trois, il n'y a plus rien à regrouper ; au-delà de six, le modèle range
#: au hasard entre des rubriques voisines, et l'écoute saute d'un groupe à l'autre.
NOMBRE_MIN = 3
NOMBRE_MAX = 6

#: Les exemples du barème 7-8 tant que le profil n'a rien déclaré : la phrase d'origine,
#: caractère pour caractère, retour à la ligne compris — elle entre dans l'empreinte.
EXEMPLES_PAR_DEFAUT = (
    "obligation à respecter, faille sur ses propres outils,\n"
    "     mouvement d'un concurrent direct"
)
#: Les mêmes, dits pour n'importe quel métier : « un concurrent direct » n'a de sens que
#: pour qui vend un logiciel, et des axes déclarés disent précisément que ce n'est pas
#: forcément le cas.
EXEMPLES_GENERIQUES = (
    "une obligation à respecter, un changement qui touche directement son travail ou ses outils"
)


class AxesError(ValueError):
    """Axes déclarés dont la liste ou une entrée n'a pas la bonne forme."""


@dataclasses.dataclass(frozen=True)
class Axe:
    """Une rubrique : le slug que le modèle rend et que le tag porte, et ce qu'elle couvre.

    Le libellé et la description ne servent qu'au prompt : c'est en les lisant que le
    modèle sait où ranger un article. Le slug, lui, est la seule chose qui revient.
    """

    slug: str
    libelle: str
    description: str


class Axes:
    """Les axes d'un profil, et ce qu'en font le prompt de scoring et sa relecture.

    La base porte ce qui ne dépend pas de leur origine — reconnaître un slug, rabattre
    une réponse hors liste, se rendre en document ; les deux sous-classes ne disent que
    ce que le prompt en montre. Le repli est le dernier axe, comme `autre` l'était.
    """

    #: Vrai seulement pour des axes écrits par la personne : ceux-là seuls s'enregistrent
    #: dans son document, le défaut ne doit pas s'y figer.
    sont_declares: bool = False

    def __init__(self, axes: Iterable[Axe]):
        self._axes = tuple(axes)

    @classmethod
    def par_defaut(cls) -> "Axes":
        """Les cinq thématiques d'origine."""
        return AxesParDefaut(Axe(slug, slug, "") for slug in THEMATIQUES)

    @classmethod
    def declares(cls, valeur: object) -> "Axes":
        """Les axes du document, ou le défaut si la clé manque. Fautifs : `AxesError`.

        Une entrée fautive lève au lieu d'être sautée : un axe disparu en silence ferait
        tomber ses articles dans le repli, et rien ne dirait pourquoi la rubrique est vide.
        """
        if valeur is None:
            return cls.par_defaut()
        if not isinstance(valeur, list) or not NOMBRE_MIN <= len(valeur) <= NOMBRE_MAX:
            raise AxesError(
                f"« {CLE_AXES} » : une liste de {NOMBRE_MIN} à {NOMBRE_MAX} axes de la forme "
                '{"slug": "cyber", "libelle": "Cybersécurité", "description": "…"}.'
            )
        axes = [_axe(entree) for entree in valeur]
        slugs = [axe.slug for axe in axes]
        doublons = sorted({slug for slug in slugs if slugs.count(slug) > 1})
        if doublons:
            raise AxesError(
                f"« {CLE_AXES} » : le slug {', '.join(doublons)} est déclaré deux fois — "
                "deux axes ne peuvent pas porter le même tag."
            )
        return AxesDeclares(axes)

    def __iter__(self) -> Iterator[Axe]:
        return iter(self._axes)

    @property
    def repli(self) -> str:
        """Le slug qui reçoit ce que le modèle n'a pas su ranger : le dernier déclaré."""
        return self._axes[-1].slug

    def contient(self, slug: object) -> bool:
        return any(axe.slug == slug for axe in self._axes)

    def rabattre(self, valeur: object) -> str:
        """La thématique rendue par le modèle, ramenée à un slug connu.

        Hors liste, le repli : un tag `theme-` inventé ne serait relu par personne, et
        l'article resterait seul dans un groupe que l'écoute ne sait pas annoncer.
        """
        candidat = str(valeur or "").strip().lower()
        return candidat if self.contient(candidat) else self.repli

    def en_document(self) -> list[dict]:
        """La liste telle que la clé `axes` du document la porte."""
        return [dataclasses.asdict(axe) for axe in self._axes]

    def consigne_thematique(self) -> str:
        """Ce que le prompt dit du champ « thematique »."""
        raise NotImplementedError

    def exemples_pertinent(self) -> str:
        """Les exemples entre parenthèses du barème 7-8."""
        raise NotImplementedError


class AxesParDefaut(Axes):
    """Les cinq d'origine : le prompt d'avant la clé, à l'octet près."""

    def consigne_thematique(self) -> str:
        return f"exactement une valeur parmi {', '.join(axe.slug for axe in self)} ;"

    def exemples_pertinent(self) -> str:
        return EXEMPLES_PAR_DEFAUT


class AxesDeclares(Axes):
    """Les axes écrits par la personne : le modèle doit lire ce que chacun couvre.

    Un slug seul ne dit rien à qui range — `qualite` couvre-t-il l'accessibilité ? —,
    d'où une ligne par axe avec son libellé et sa description.
    """

    sont_declares = True

    def consigne_thematique(self) -> str:
        lignes = ["exactement un slug parmi les axes de veille ci-dessous, recopié tel quel ;"]
        lignes.extend(f"  - {axe.slug} ({axe.libelle}) : {axe.description}" for axe in self)
        return "\n".join(lignes)

    def exemples_pertinent(self) -> str:
        return EXEMPLES_GENERIQUES


def _axe(entree: object) -> Axe:
    """Une entrée de la liste relue en `Axe`, sa forme étant exigée."""
    if not isinstance(entree, dict):
        raise AxesError(
            f"« {CLE_AXES} » : un axe est un objet "
            '{"slug": "cyber", "libelle": "Cybersécurité", "description": "…"}.'
        )
    slug = entree.get("slug")
    if not isinstance(slug, str) or not MOTIF_SLUG.match(slug):
        raise AxesError(
            f"« {CLE_AXES} » : slug invalide « {slug} ». Attendu : 2 à 24 caractères, "
            "minuscules, chiffres ou « - », commençant par une lettre — il devient le tag "
            "FreshRSS theme-<slug>."
        )
    for champ in ("libelle", "description"):
        texte = entree.get(champ)
        if not isinstance(texte, str) or not texte.strip():
            raise AxesError(
                f"Axe « {slug} » : « {champ} » attend un texte non vide — c'est en le "
                "lisant que le modèle sait quoi ranger sous cet axe."
            )
    return Axe(slug, entree["libelle"].strip(), entree["description"].strip())
