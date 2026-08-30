"""Poser les liens des articles retenus dans le texte du résumé, sur un mot qui les rappelle.

Le résumé ne cite aucune URL — il part aussi en synthèse vocale, et une URL lue à voix
haute est inutilisable. Les liens vivaient donc dans une liste, sous le texte : pour
retrouver l'article derrière un sujet, il fallait relire le titre en bas et faire le
rapprochement soi-même.

Ce module fait ce rapprochement à l'écrit. Il cherche, dans le résumé, le groupe de mots
le plus distinctif du titre de chaque article retenu, et rend de quoi le rendre
cliquable là où il est dit. « Une faille critique touche **Traefik** » mène à l'avis du
CERT-FR sans qu'on ait à descendre.

Rien n'est demandé au modèle, et le texte du résumé n'est pas touché d'un caractère :
c'est un appariement fait après coup, sur ce qui est déjà écrit. La synthèse vocale lit
donc exactement le même texte qu'avant, et un lien mal posé ne peut jamais être un lien
inventé — l'URL vient de la sélection, comme celles de la liste.

L'appariement est au mieux, jamais garanti : un article dont le résumé ne reprend aucun
nom propre ne s'ancre nulle part. C'est pourquoi la liste « À lire » reste sous le
texte — elle, ne rate personne.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Iterable

from rssresume.models import Link

#: Longueur minimale d'une ancre d'un seul mot. En dessous, le mot est trop court pour
#: désigner quoi que ce soit — sauf s'il est un sigle, traité à part.
LONGUEUR_MIN = 4

#: Longueur minimale d'un sigle. « NG », « MF » ne rappellent aucun titre ; « CVE »,
#: « KEV », « AWS » si.
SIGLE_MIN = 3

#: Mots qui portent une majuscule sans rien désigner : début de phrase en français,
#: casse de titre en anglais. Sans cette liste, « Enfin, deux correctifs » offrirait
#: « Enfin » comme ancre au premier titre qui commence par le même mot.
COURANTS = """
    le la les un une des du de d au aux ce cet cette ces son sa ses leur leurs
    il elle ils elles on nous vous je tu me te se y en
    et ou mais donc or ni car que qui quoi dont où quand comme si
    dans sur sous pour par avec sans chez vers entre depuis après avant pendant
    enfin ensuite puis aussi encore déjà plus moins très trop peu beaucoup bien
    tout tous toute toutes autre autres même mêmes chaque plusieurs certains
    alors ainsi cependant toutefois néanmoins pourtant selon côté rien
    un deux trois quatre cinq six sept huit neuf dix cent mille premier première
    lundi mardi mercredi jeudi vendredi samedi dimanche
    janvier février mars avril mai juin juillet août septembre octobre novembre décembre
    the a an and or but for with without from to in on at by of as is are was were be been
    this that these those it its they their he she we you not no only also then than
    new now more most less least all any some when where what which who how why
    can could may might will would should must has have had does did
    one two three four five six seven eight nine ten
"""

#: Les sigles du domaine, qui reviennent dans un titre sur deux. Ils nomment une classe
#: de problème, jamais un article : « RCE » posé sur la première phrase qui le contient
#: mènerait à un tout autre sujet que celui dont elle parle. C'est le défaut le plus
#: coûteux que ce module puisse produire, puisqu'il donne un lien plausible et faux.
#:
#: Un identifiant complet — CVE-2021-44228 — n'est pas concerné : il porte des chiffres,
#: ne ressemble à rien d'autre, et fait au contraire la meilleure ancre qui soit.
SIGLES_COURANTS = """
    rce cve dos ddos api vpn saas iaas paas mfa sso os pc it ia ai
    http https url dns tls ssl pdf xss csrf poc cvss
"""

BANALS = frozenset(COURANTS.split()) | frozenset(SIGLES_COURANTS.split())

#: L'élision française, en tête de mot. Sans elle, « 700 agents d'OpenAI » ne livre que
#: le mot « d'OpenAI », qui ne commence pas par une majuscule et passe donc pour banal :
#: le nom propre disparaît derrière son apostrophe, et l'article perd son ancre. La
#: recherche dans le résumé, elle, n'a pas ce problème — une apostrophe est une
#: frontière de mot, et « OpenAI » s'y retrouve tel quel.
ELISION = re.compile(r"^(?:qu|[cdjlmnst])['’]", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class Segment:
    """Un morceau de résumé : du texte nu, ou du texte qui porte un lien.

    Le rendu ne reçoit pas du HTML tout fait mais cette découpe : c'est ce qui permet de
    l'échapper lui-même, morceau par morceau, sans avoir à démêler ce qui est balise de
    ce qui vient d'un flux.
    """

    texte: str
    #: Vide pour un segment de texte nu.
    url: str = ""


def ancrer(texte: str, liens: Iterable[Link]) -> list[Segment]:
    """Découpe le résumé ENTIER en segments, ceux qui portent un lien et les autres.

    Le résumé entier et non paragraphe par paragraphe, et c'est le point important :
    un article dont le premier paragraphe ne dit qu'un sigle et le troisième le nom
    propre doit s'ancrer sur le nom propre. Placé paragraphe par paragraphe, il se
    serait posé dans le premier, sur le sigle, à côté d'un sujet qui n'est pas le sien.
    """
    poses = _placer(texte, list(liens))
    if not poses:
        return [Segment(texte)]

    segments: list[Segment] = []
    curseur = 0
    for debut, fin, lien in poses:
        if debut > curseur:
            segments.append(Segment(texte[curseur:debut]))
        segments.append(Segment(texte[debut:fin], lien.url))
        curseur = fin
    if curseur < len(texte):
        segments.append(Segment(texte[curseur:]))
    return segments


def _placer(texte: str, liens: list[Link]) -> list[tuple[int, int, Link]]:
    """Où poser chaque lien dans le texte, sans chevauchement, dans l'ordre de lecture.

    L'attribution est gourmande et prend les meilleures ancres d'abord : un groupe de
    deux mots désigne bien mieux un article qu'un mot seul, et il doit donc pouvoir
    réserver sa place avant qu'un mot isolé ne la prenne. Deux articles qui visent le
    même endroit — deux dépêches sur la même faille — sont départagés là : le premier
    servi le garde, l'autre se rabat sur une autre ancre ou reste dans la liste.
    """
    candidats = []
    for rang, lien in enumerate(liens):
        for ancre in ancres_du_titre(lien.title):
            trouve = _chercher(texte, ancre)
            if trouve:
                debut, fin = trouve
                # Le rang départage à ancre égale : l'ordre du digest, donc du score.
                candidats.append((-len(ancre.split()), -len(ancre), rang, debut, fin, lien))
                break

    retenus: list[tuple[int, int, Link]] = []
    servis: set[int] = set()
    for *_, debut, fin, lien in sorted(candidats):
        if id(lien) in servis:
            continue
        if any(debut < f and d < fin for d, f, _ in retenus):
            continue
        retenus.append((debut, fin, lien))
        servis.add(id(lien))
    return sorted(retenus)


def _chercher(texte: str, ancre: str) -> tuple[int, int] | None:
    """La première occurrence de l'ancre dans le texte, aux frontières de mot.

    La casse compte : ce sont des noms propres qu'on cherche, et « Ring » n'est pas
    « ring ». L'espacement, lui, est souple — le titre sépare ses mots d'une espace,
    le résumé peut passer à la ligne au même endroit. Jamais au travers d'un paragraphe
    en revanche : un lien à cheval sur deux `<p>` ne se referme nulle part.
    """
    motif = r"[^\S\n]*\n?[^\S\n]*".join(re.escape(mot) for mot in ancre.split())
    trouve = re.search(rf"(?<!\w){motif}(?!\w)", texte)
    return (trouve.start(), trouve.end()) if trouve else None


def ancres_du_titre(titre: str) -> list[str]:
    """Les groupes de mots distinctifs d'un titre, du plus long au plus court.

    « CISA orders feds to patch Citrix NetScaler RCE flaw » rend « Citrix NetScaler »,
    puis « Citrix », « NetScaler », « CISA », « RCE ». Le plus long est essayé d'abord :
    c'est celui qui désigne le mieux, et celui qu'un autre article a le moins de chances
    de revendiquer aussi.

    Les titres anglais sont en casse de titre, où presque tout mot porte une majuscule.
    Ce n'est pas un problème : les faux candidats qu'elle produit — « Adds », « Flaws » —
    ne figurent pas dans un résumé écrit en français, et ne se posent donc nulle part.
    """
    suites = _suites_distinctives(titre)
    candidats = {
        " ".join(suite[debut:fin])
        for suite in suites
        for debut in range(len(suite))
        for fin in range(debut + 1, len(suite) + 1)
    }
    retenus = [ancre for ancre in candidats if _utilisable(ancre)]
    # Du plus long au plus court, en mots puis en caractères : à nombre de mots égal,
    # « NetScaler » désigne mieux que « Linux ».
    return sorted(retenus, key=lambda ancre: (-len(ancre.split()), -len(ancre), ancre))


def _suites_distinctives(titre: str) -> list[list[str]]:
    """Les suites de mots distinctifs consécutifs du titre.

    Consécutifs, parce que c'est ce qui fait un nom composé : « SQL Server » n'a de sens
    que collé, et sauter un mot banal fabriquerait des groupes que personne n'écrit.
    """
    suites: list[list[str]] = []
    courante: list[str] = []
    for brut in re.findall(r"[^\W_]+(?:[.'\-][^\W_]+)*", titre, re.UNICODE):
        mot = ELISION.sub("", brut)
        if _distinctif(mot):
            courante.append(mot)
        elif courante:
            suites.append(courante)
            courante = []
    if courante:
        suites.append(courante)
    return suites


def _distinctif(mot: str) -> bool:
    """Vrai pour un mot qui peut désigner quelque chose : un nom propre, un sigle, une référence."""
    if mot.casefold() in BANALS:
        return False
    if any(caractere.isdigit() for caractere in mot):
        # « Log4Shell », « CVE-2021-44228 », « 7.4.5 » : un chiffre dans un mot est
        # presque toujours une référence, et une référence est une excellente ancre.
        return True
    return mot[:1].isupper()


def _utilisable(ancre: str) -> bool:
    """Vrai pour une ancre assez spécifique pour être posée sur un texte.

    Un mot seul doit être long, ou être un sigle, ou porter un chiffre. En dessous, le
    risque de tomber sur un mot du résumé qui parle d'autre chose l'emporte sur le
    service rendu — et un lien qui mène ailleurs est pire que pas de lien du tout.
    """
    mots = ancre.split()
    if len(mots) > 1:
        return True
    mot = mots[0]
    if any(caractere.isdigit() for caractere in mot):
        return True
    if mot.isupper():
        return len(mot) >= SIGLE_MIN
    return len(mot) >= LONGUEUR_MIN
