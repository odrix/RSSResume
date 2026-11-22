"""L'audio unique d'une journée : un seul texte pour tous les sujets, toutes catégories.

Le montage enchaînait les résumés de catégorie déjà écrits, dans l'ordre des catégories.
Un seul fichier, une seule voix — mais l'ordre restait celui des dossiers FreshRSS : le
sujet le plus grave de la matinée pouvait tomber en huitième position parce que sa
catégorie était la dernière, et deux articles qui parlaient de la même chose depuis deux
catégories différentes restaient séparés par tout le reste de la journée.

Il part donc maintenant des **sujets**, pas des résumés : les articles retenus de toutes
les catégories, remis dans un seul ordre — score décroissant, sujets connexes côte à
côte (`models.groupees_par_thematique`). C'est une passe de rédaction sur la source, plus
un second passage sur du texte déjà résumé : les numéros de version ne traversent plus
deux réécritures, et la fusion des doublons se fait là où elle a du sens, sur des
articles et non sur de la prose.

Les résumés de catégorie ne disparaissent pas pour autant : c'est eux que l'email montre,
et c'est eux que l'assemblage local remet bout à bout quand aucun modèle n'est joignable.
Ce que l'œil lit et ce que l'oreille entend sont deux textes, écrits pour deux usages.

Les catégories déterministes font exception : leur constat est déjà rédigé, sans modèle,
et se relaie tel quel plutôt que d'être refait — refaire un tri déterministe avec un LLM
est exactement ce que `rssresume/certfr/` a été écrit pour éviter.

Un module à part de `summaries.py`, et non une méthode de plus dedans : d'un côté le
résumé d'une catégorie, écrit pour être lu ; de l'autre la journée entière, écrite pour
être entendue d'une traite — avec sa salutation, son éphéméride et sa conclusion. Et
deux actions distinctes chez le fournisseur, donc deux postes de dépense.

Le couple `MontageService` / `models.Montage` suit celui de `EphemerideService` /
`models.Ephemeride` : un service qui sait descendre d'une marche quand le modèle manque,
et un objet de valeur que le journal écrit et que `--send-only` relit.
"""

from __future__ import annotations

from rssresume.certfr import Stack
from rssresume.config import DEFAULT_ARTICLE_CHAR_LIMIT
from rssresume.llm import LLMError, LLMProvider
from rssresume.models import (
    ORIGINE_ASSEMBLAGE,
    ORIGINE_MONTAGE,
    Article,
    CategoryDigest,
    Ephemeride,
    Montage,
    Note,
    groupees_par_thematique,
)
from rssresume.newsletter import date_longue
from rssresume.profil import SECURITE_PAR_DEFAUT, Securite
from rssresume.tools import console
from rssresume.tools.text import truncate_sentences


class MontageService:
    """Écrit le texte que la voix dira, pour la journée entière.

    Sans fournisseur — aucune clé d'API, ou l'action confiée à un fournisseur qui n'en a
    pas —, l'assemblage local prend la suite : le mode `global` reste utilisable sur une
    installation sans IA, comme le résumé de catégorie l'est déjà.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        language: str = "fr",
        profil: str | None = None,
        prenom: str = "",
        char_limit: int = DEFAULT_ARTICLE_CHAR_LIMIT,
        stack: Stack | None = None,
        securite: Securite = SECURITE_PAR_DEFAUT,
    ):
        self._provider = provider
        self._language = language
        self._profil = profil
        #: Vide, la salutation ne nomme personne. C'est une salutation en moins, pas une
        #: erreur : la clé `prenom` du document de profil est facultative.
        self._prenom = prenom
        #: Le même plafond que celui du résumé de catégorie : cette passe lit désormais
        #: les mêmes articles, et c'est le seul chemin d'entrée qu'il reste à borner.
        self._char_limit = char_limit
        #: Les composants exploités, pour la seule règle qui en dépend : le détail donné
        #: sur les versions d'une CVE selon qu'elle touche ou non ce qui tourne chez soi.
        self._stack = stack if stack is not None else Stack()
        #: Le régime de sécurité du document, qui module ce même détail : le même que
        #: celui du résumé de catégorie, pour que l'œil et l'oreille disent pareil.
        self._securite = securite

    def ecrire(
        self, ephemeride: Ephemeride | None, digests: list[CategoryDigest]
    ) -> Montage:
        """Le texte de la journée, écrit d'une traite depuis les sujets de toutes les catégories.

        Le jour dont il est question est celui de l'éphéméride — le jour de l'ENVOI, pas
        celui que le digest raconte. C'est déjà le jour sur lequel l'email s'ouvre, et
        deux dates différentes à l'œil et à l'oreille ne s'expliqueraient pas.
        """
        racontees, muettes = self._trier(digests)
        if not racontees:
            # Rien à dire : pas de texte, donc pas d'audio. Une salutation suivie d'un
            # silence est pire qu'une pièce jointe absente, et l'email dit déjà que la
            # journée est vide.
            return Montage(texte="", origine=ORIGINE_ASSEMBLAGE)

        jour = self._jour(ephemeride)
        sections = self._sections(racontees)
        if self._provider is None:
            return self._assembler(jour, sections, muettes)

        sujets = self._sujets(racontees)
        constats = [
            digest.summary_text.strip() for digest in racontees if digest.deterministe
        ]
        if not sujets and not constats:
            # Toutes les catégories racontées sont passées par un modèle absent au moment
            # de la sélection : il n'y a ni article ni constat à dire.
            return self._assembler(jour, sections, muettes)

        console.detail(
            f"montage via {self._provider.name} — {self._provider.model('montage')} "
            f"({len(sujets)} sujet(s) toutes catégories, {len(constats)} constat(s))"
        )
        try:
            texte = self._provider.write_montage(
                sujets,
                jour,
                constats,
                muettes,
                self._language,
                self._profil,
                self._prenom,
                not self._stack.vide,
                securite=self._securite,
            )
        except LLMError as exc:
            # La journée est déjà payée : scoring, résumés, tags. La perdre parce que le
            # dernier appel a échoué serait le plus cher des abandons — et l'assemblage
            # dit la même chose, moins bien. `origine` garde la trace de la marche perdue.
            console.detail(f"montage indisponible ({exc}) — assemblage local des résumés")
            return self._assembler(jour, sections, muettes)
        return Montage(texte=texte.strip(), origine=ORIGINE_MONTAGE)

    def _sujets(self, racontees: list[CategoryDigest]) -> list[dict]:
        """Les articles retenus de toutes les catégories, dans l'ordre où ils se racontent.

        L'ordre est refait à l'échelle de la journée et non hérité des catégories : c'est
        toute la différence entre un seul fichier et un seul récit. La catégorie d'origine
        n'accompagne pas le sujet, délibérément — elle n'a plus rien à décider une fois
        l'ordre posé, et un modèle qui la voit finit par l'annoncer.
        """
        notes: dict[str, Note] = {}
        articles: list[Article] = []
        for digest in racontees:
            if digest.deterministe:
                # Son constat est déjà écrit, et ses avis n'ont pas été notés : ils
                # n'ont ni score ni thématique à faire valoir dans l'ordre du jour.
                continue
            notes.update(digest.notes)
            articles.extend(digest.selected)
        return [
            self._sujet(article, notes.get(article.item_id))
            for article in groupees_par_thematique(articles, notes)
        ]

    def _sujet(self, article: Article, note: Note | None) -> dict:
        """Un sujet tel qu'il part au montage : le même payload que celui du résumé.

        Le même, et c'est voulu : les deux textes doivent dire les mêmes faits, et deux
        façons de préparer un article finiraient par ne plus donner à lire et à entendre
        la même journée. Ni URL ni nom de flux, pour la raison habituelle — ce qui n'est
        pas dans le contexte ne peut pas être prononcé.
        """
        sujet = {
            "title": article.title,
            "content": truncate_sentences(article.content_text, self._char_limit),
        }
        concernes = self._stack.concernes(f"{article.title}\n{article.content_text}")
        if concernes:
            sujet["stack"] = list(concernes)
        if note:
            sujet["score"] = note.score
            sujet["thematique"] = note.thematique
            if note.angle:
                # Absent des articles dont le score vient du cache de tags.
                sujet["angle"] = note.angle
        return sujet

    @staticmethod
    def _sections(racontees: list[CategoryDigest]) -> list[dict]:
        """Les résumés déjà écrits, pour le seul assemblage local.

        Ils ne partent plus au modèle — il travaille sur les articles — mais ils restent
        ce que le repli met bout à bout : sans fournisseur, il n'y a personne pour rédiger
        quoi que ce soit, et ces textes-là existent déjà.
        """
        return [
            {"categorie": digest.category, "resume": digest.summary_text.strip()}
            for digest in racontees
        ]

    @staticmethod
    def _trier(
        digests: list[CategoryDigest],
    ) -> tuple[list[CategoryDigest], list[str]]:
        """Les catégories qui ont quelque chose à dire, et le nom des autres.

        Le discriminant est `marker_path` et non `selected`. Une catégorie sans article,
        ou dont rien n'a passé le seuil, porte son marqueur `.no-article` et un
        `summary_text` qui est une phrase de plomberie — « Aucun article retenu sur 3
        (seuil 7) » : la donner au montage la ferait lire à voix haute. Une catégorie
        CERT-FR dont aucun avis ne touche la stack, elle, n'a pas de marqueur et sa
        phrase est un vrai résultat, qui mérite d'être entendu — `selected` l'aurait
        écartée avec les autres.
        """
        racontees, muettes = [], []
        for digest in digests:
            if digest.marker_path is None and digest.summary_text.strip():
                racontees.append(digest)
            else:
                muettes.append(digest.category)
        return racontees, muettes

    @staticmethod
    def _jour(ephemeride: Ephemeride | None) -> str:
        """La date, sa fête et son fait, dans la tournure même de l'email.

        `date_longue` et l'apposition de la fête viennent de la lettre : l'œil et
        l'oreille reçoivent le même jour dans les mêmes mots, et la table des jours et
        des mois n'existe qu'à un seul endroit.
        """
        if ephemeride is None:
            return ""
        fete = (ephemeride.fete or "").strip()
        ligne = date_longue(ephemeride.jour).capitalize() + (f", {fete}." if fete else ".")
        return " ".join(part for part in (ligne, (ephemeride.texte or "").strip()) if part)

    def _assembler(self, jour: str, sections: list[dict], muettes: list[str]) -> Montage:
        """Le repli : la salutation, le jour, les résumés à la suite, et rien de plus.

        Ni transitions ni conclusion. Les fabriquer sans modèle produirait exactement la
        formule passe-partout que le prompt interdit — « restez vigilant » —, et une
        conclusion fausse est pire qu'une conclusion absente. L'audio du jour sort quand
        même, et `origine` dit qu'il a été monté à la main.
        """
        console.detail(f"montage local, sans IA ({len(sections)} catégorie(s))")
        salutation = f"Bonjour {self._prenom}." if self._prenom else "Bonjour."
        blocs = [salutation, jour, *(section["resume"] for section in sections)]
        if muettes:
            blocs.append(f"Rien à signaler du côté de : {', '.join(muettes)}.")
        return Montage(
            texte="\n\n".join(bloc for bloc in blocs if bloc),
            origine=ORIGINE_ASSEMBLAGE,
        )
