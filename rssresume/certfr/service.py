"""Le tri déterministe d'une journée d'avis CERT-FR : apparier, graduer, rédiger.

Pourquoi ces avis ne passent pas par le LLM. Le flux « CERT-FR - Avis de securite » en
publie cinq à dix par jour, tous bâtis sur le même moule : un titre « Multiples
vulnérabilités dans <Produit> (JJ mois AAAA) » et une description d'une phrase. Payer un
scoring puis un résumé pour cela revient à faire reformuler un formulaire ; et à
l'écoute, sept paragraphes qui commencent tous pareil sont exactement ce qu'on n'écoute
pas. Ce qui manquait n'était pas un résumé, c'était une réponse : est-ce que ça me
touche, moi.

D'où trois opérations, toutes hors modèle :

1. **apparier** le titre et la description sur la liste des composants (`stack.py`) ;
2. **graduer** l'avis sur l'impact que le CERT-FR y annonce lui-même — la description
   d'un avis nomme ce que la faille permet, dans un vocabulaire fixe : « exécution de
   code arbitraire à distance », « élévation de privilèges », « déni de service » ;
3. **rédiger** une phrase, une seule, qui liste ce qui touche la stack et à quel titre.

Aucun de ces trois pas ne peut inventer. C'est le point : sur un avis de sécurité, une
information fabriquée est pire que pas d'information.
"""

from __future__ import annotations

from typing import Iterable

from rssresume.certfr.stack import Stack, charger
from rssresume.models import Article
from rssresume.tools.text import contains_words, words


class Criticite:
    """Un impact tel que le CERT-FR le nomme, et le rang qu'on lui donne.

    Le rang n'est pas une échelle du CERT-FR : ses avis ne portent ni score CVSS ni
    cotation de gravité, seulement la liste de ce que la faille permet. C'est donc un
    classement local, celui de l'exploitant — prendre la main devant la couper — et il
    ne sert qu'à mettre en tête de la phrase l'avis qu'on veut lire en premier.
    """

    def __init__(self, rang: int, libelle: str):
        self.rang = rang
        #: Ce qui s'écrit dans la phrase du digest, et ce que l'on cherche dans l'avis :
        #: un seul texte pour les deux, sans quoi la phrase finirait par nommer autre
        #: chose que ce qui a été reconnu.
        self.libelle = libelle
        self._forme = words(libelle)

    def annoncee_dans(self, mots: tuple[str, ...]) -> bool:
        return contains_words(mots, self._forme)


#: Les impacts du vocabulaire CERT-FR, du plus grave au moins grave. L'ordre est ce qui
#: fait tout le travail : la reconnaissance s'arrête au premier qui répond, et « exécution
#: de code arbitraire à distance » est cherché avant « exécution de code arbitraire »,
#: dont il contient les mots. Inverser deux lignes change le résultat.
#:
#: Plusieurs libellés partagent un rang : ce sont des impacts distincts, que le CERT-FR
#: nomme distinctement, et qu'on ne veut pas départager. Chacun a son entrée plutôt que
#: d'être la variante d'un autre — la phrase du digest nomme ce qui a été reconnu, elle
#: ne le traduit pas.
ECHELLE = (
    Criticite(9, "exécution de code arbitraire à distance"),
    Criticite(8, "exécution de code arbitraire"),
    Criticite(7, "élévation de privilèges"),
    Criticite(6, "contournement de la politique de sécurité"),
    Criticite(6, "contournement de l'authentification"),
    Criticite(6, "contournement de la fonctionnalité de sécurité"),
    Criticite(5, "injection de code indirecte à distance"),
    Criticite(5, "injection SQL"),
    Criticite(5, "falsification de requêtes côté serveur"),
    Criticite(4, "atteinte à l'intégrité des données"),
    Criticite(3, "atteinte à la confidentialité des données"),
    Criticite(2, "déni de service à distance"),
    Criticite(1, "déni de service"),
)

#: Ce qu'on écrit quand la description n'annonce aucun impact connu — un bulletin
#: d'actualité, un avis dont l'éditeur n'a rien spécifié, une tournure inédite. Un repli
#: nommé plutôt qu'un champ vide : la phrase doit dire qu'elle ne sait pas, sinon le
#: lecteur croit à une faille bénigne.
INDETERMINEE = Criticite(0, "impact non précisé par l'avis")


def criticite_de(texte: str) -> Criticite:
    """L'impact le plus grave que ce texte annonce, `INDETERMINEE` s'il n'en nomme aucun."""
    mots = words(texte)
    for criticite in ECHELLE:
        if criticite.annoncee_dans(mots):
            return criticite
    return INDETERMINEE


class Avis:
    """Un avis apparié : l'article, ce qu'il touche chez nous, et à quel titre."""

    def __init__(self, article: Article, composants: tuple[str, ...], criticite: Criticite):
        self.article = article
        self.composants = composants
        self.criticite = criticite

    @property
    def dit(self) -> str:
        """« Keycloak — élévation de privilèges », le fragment que la phrase enfile.

        Le composant et non le titre de l'avis : le titre est déjà dans la liste « À
        lire » de l'email, mot pour mot, et il dit « Multiples vulnérabilités dans X »
        là où on veut lire X. Un avis qui touche deux composants les nomme tous les deux
        — c'est précisément le jour où l'on veut le savoir.
        """
        return f"{_enumere(self.composants)} — {self.criticite.libelle}"


class Revue:
    """Ce que le tri déterministe a fait d'une journée d'avis.

    Elle porte les trois nombres dont la phrase a besoin — les avis lus, ceux qui
    touchent, les composants surveillés — parce qu'une phrase qui dirait « 2 avis vous
    concernent » sans dire sur combien ne se juge pas. Deux sur deux et deux sur trente
    ne se lisent pas de la même façon à sept heures du matin.
    """

    def __init__(self, avis: Iterable[Avis], lus: int, composants: int):
        self.avis = list(avis)
        self.lus = lus
        self.composants = composants

    @property
    def touches(self) -> list[Article]:
        """Les articles à faire remonter dans les liens « À lire », les plus graves devant."""
        return [avis.article for avis in self.avis]

    @property
    def phrase(self) -> str:
        """La sortie de la catégorie : une phrase, celle que l'email affiche.

        Trois cas, et le premier n'est pas une politesse : une stack vide n'apparie rien,
        et rendre le même « rien ne vous touche » que les autres jours ferait passer une
        configuration jamais remplie pour une bonne nouvelle quotidienne.
        """
        if not self.composants:
            return (
                f"{self._avis_lus} sans appariement : aucun composant n'est déclaré "
                f"dans la liste de la stack."
            )
        if not self.avis:
            return f"{self._avis_lus}, aucun ne touche {self._surveilles}."
        verbe = "touche" if len(self.avis) == 1 else "touchent"
        detail = " ; ".join(avis.dit for avis in self.avis)
        return f"{self._avis_lus}, {len(self.avis)} {verbe} la stack : {detail}."

    @property
    def _avis_lus(self) -> str:
        """« 7 avis CERT-FR aujourd'hui ». « avis » est invariable, le compte suffit."""
        return f"{self.lus} avis CERT-FR aujourd'hui"

    @property
    def _surveilles(self) -> str:
        """« les 4 composants surveillés », ou « le seul composant surveillé ».

        Le compte n'est pas décoratif : il dit sur quelle largeur la comparaison a
        porté, et une stack d'un seul composant est un réglage qu'on veut voir. Mais
        « les 1 composant » ne se lit pas, et la phrase est lue à voix haute.
        """
        if self.composants == 1:
            return "le seul composant surveillé"
        return f"les {self.composants} composants surveillés"


class CertfrService:
    """Le traitement déterministe d'une catégorie d'avis CERT-FR.

    Le collaborateur que `DigestService` appelle à la place du noteur, du résumeur et de
    la synthèse vocale pour les catégories que `RSSRESUME_CERTFR_CATEGORIES` désigne. Il
    ne parle à personne : aucun réseau, aucun modèle, aucun coût.

    La stack est injectée au constructeur, comme partout ailleurs ici ; sans argument,
    c'est celle du fichier livré, surchargée par `RSSRESUME_STACK_FILE`.
    """

    def __init__(self, stack: Stack | None = None):
        self._stack = charger() if stack is None else stack

    @property
    def stack(self) -> Stack:
        """La liste contre laquelle la journée est appariée, que le journal fixe."""
        return self._stack

    def lire(self, articles: list[Article]) -> Revue:
        """Trie une journée d'avis : ceux qui touchent la stack, les plus graves devant.

        Le tri est stable : à impact égal, l'ordre reste celui du flux, c'est-à-dire
        celui de publication. Deux exécutions de la même journée rendent donc la même
        phrase, mot pour mot — c'est ce qui rend `--send-only` et le journal comparables.
        """
        apparies = [avis for avis in (self._avis(article) for article in articles) if avis]
        apparies.sort(key=lambda avis: avis.criticite.rang, reverse=True)
        return Revue(apparies, lus=len(articles), composants=len(self._stack))

    def _avis(self, article: Article) -> Avis | None:
        """L'avis apparié, `None` s'il ne touche aucun composant.

        Le titre ET la description : le titre nomme le produit dans la quasi-totalité des
        avis, mais un avis « Multiples vulnérabilités dans les produits IBM » ne nomme le
        composant réellement touché que dans son texte.
        """
        texte = f"{article.title}\n{article.content_text}"
        composants = self._stack.concernes(texte)
        if not composants:
            return None
        return Avis(article, composants, criticite_de(texte))


def _enumere(noms: tuple[str, ...]) -> str:
    """« A », « A et B », « A, B et C ». La virgule jusqu'au dernier, qui prend « et »."""
    if len(noms) <= 1:
        return "".join(noms)
    return f"{', '.join(noms[:-1])} et {noms[-1]}"
