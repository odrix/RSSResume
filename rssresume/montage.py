"""L'audio unique d'une journée : un seul texte pour toutes les catégories.

Un second passage, et il faut qu'il le reste. Les résumés de catégorie sont déjà écrits
et partent tels quels dans l'email : le montage ne les remplace pas, il les enchaîne —
une salutation devant, l'éphéméride du jour, des transitions entre les catégories, et
une conclusion sur ce qui reste à faire.

Un module à part de `summaries.py`, et non une méthode de plus dedans : rien n'y
ressemble. D'un côté un résumé d'articles, de l'autre un montage de résumés ; d'un côté
un repli extractif qui relit du contenu de flux, de l'autre un assemblage qui n'en relit
aucun ; et deux actions distinctes chez le fournisseur, donc deux postes de dépense.

Le couple `MontageService` / `models.Montage` suit celui de `EphemerideService` /
`models.Ephemeride` : un service qui sait descendre d'une marche quand le modèle manque,
et un objet de valeur que le journal écrit et que `--send-only` relit.
"""

from __future__ import annotations

from rssresume.llm import LLMError, LLMProvider
from rssresume.models import (
    ORIGINE_ASSEMBLAGE,
    ORIGINE_MONTAGE,
    CategoryDigest,
    Ephemeride,
    Montage,
)
from rssresume.newsletter import date_longue
from rssresume.tools import console


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
    ):
        self._provider = provider
        self._language = language
        self._profil = profil
        #: Vide, la salutation ne nomme personne. C'est une salutation en moins, pas une
        #: erreur : la clé `prenom` du document de profil est facultative.
        self._prenom = prenom

    def ecrire(
        self, ephemeride: Ephemeride | None, digests: list[CategoryDigest]
    ) -> Montage:
        """Le texte de la journée, monté depuis les résumés déjà produits.

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
        sections = [
            {"categorie": digest.category, "resume": digest.summary_text.strip()}
            for digest in racontees
        ]
        if self._provider is None:
            return self._assembler(jour, sections, muettes)

        console.detail(
            f"montage via {self._provider.name} — {self._provider.model('montage')} "
            f"({len(sections)} catégorie(s) enchaînée(s))"
        )
        try:
            texte = self._provider.write_montage(
                sections, jour, muettes, self._language, self._profil, self._prenom
            )
        except LLMError as exc:
            # La journée est déjà payée : scoring, résumés, tags. La perdre parce que le
            # dernier appel a échoué serait le plus cher des abandons — et l'assemblage
            # dit la même chose, moins bien. `origine` garde la trace de la marche perdue.
            console.detail(f"montage indisponible ({exc}) — assemblage local des résumés")
            return self._assembler(jour, sections, muettes)
        return Montage(texte=texte.strip(), origine=ORIGINE_MONTAGE)

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
