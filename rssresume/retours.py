"""Les retours sur une journée : « utile » ou « pas utile », et un commentaire libre.

La bêta n'a de sens que si les retours arrivent. Le pied de la lettre porte donc deux
liens, un par avis, qui mènent à une page du site sans connexion : un destinataire ajouté
par un autre n'a pas de compte, et c'est pourtant lui qu'on veut entendre. La page des
résumés porte les mêmes boutons pour qui est connecté.

Un vote vaut pour un profil et une journée — la journée que la lettre RACONTE, celle de
son titre, et non le jour de l'envoi : c'est elle qu'on juge. Un second vote sur la même
journée remplace le premier, d'où qu'il vienne.

Le lien est signé comme celui du désabonnement, et pour les mêmes raisons : rien à
stocker, et `--send-only` rend la même lettre. `Signataire` reste pour l'instant dans
`desabonnement.py` : deux liens signés ne justifient pas encore un module à part, un
troisième le fera.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum

from rssresume.desabonnement import JetonInvalide, Signataire
from rssresume.profil import ChampInvalide

#: L'usage de la clé : un jeton de désabonnement n'est jamais un jeton de vote, ni l'inverse.
OBJET_RETOUR = "retour"

#: La version du format, signée avec le reste, comme pour le désabonnement.
VERSION = "v1"

#: Assez pour dire pourquoi une journée n'a pas servi ; trop peu pour y coller un document.
#: Comptée en caractères (points de code), comme le site la compte : un emoji vaut un.
LONGUEUR_MAX_COMMENTAIRE = 2000

#: Ce que `/admin` montre, les plus récents d'abord. Une borne fixe plutôt qu'une
#: pagination : la bêta ne produira pas de quoi la dépasser de sitôt, et la liste sans
#: borne grossirait la page en silence le jour où elle le ferait.
LIMITE_LISTE_RETOURS = 200


class Avis(enum.Enum):
    """Les deux réponses possibles. Deux et pas une note : on veut savoir si la journée a
    servi, et une échelle demanderait de deviner ce que vaut un « 3 »."""

    UTILE = "utile"
    PAS_UTILE = "pas_utile"

    @property
    def libelle(self) -> str:
        return "Utile" if self is Avis.UTILE else "Pas utile"


@dataclasses.dataclass(frozen=True)
class JourneeVisee:
    """Ce qu'un lien de vote désigne : un profil et une journée, rien d'autre.

    L'avis n'en fait pas partie : il passe en paramètre de l'URL, en clair. Signé, il
    aurait fallu deux jetons par lettre pour la même autorisation — voter sur cette
    journée —, et la page laisse de toute façon changer d'avis avant d'envoyer.
    """

    profil_id: str
    jour: dt.date


@dataclasses.dataclass(frozen=True)
class Retour:
    """Un vote sur une journée, tel que la base le garde et que `/admin` le montre."""

    profil_id: str
    jour: dt.date
    avis: Avis
    commentaire: str
    #: Posé par la base à l'enregistrement : c'est elle qui date, pas qui saisit.
    vote_le: str | None = None
    #: Le nom du profil, pour l'affichage. `None` quand le profil a disparu depuis : le
    #: retour reste, il a été donné.
    username: str | None = None

    @classmethod
    def saisi(cls, profil_id: str, jour: dt.date, saisie: object) -> "Retour":
        """Le retour d'un corps JSON `{avis, commentaire?}`, validé.

        Le profil et la journée ne sont jamais lus dans la saisie : ils viennent du jeton
        signé, ou de l'URL que le site a déjà contrôlée. Un commentaire trop long est
        refusé plutôt que tronqué : couper la fin d'un texte sans le dire, c'est en perdre
        la conclusion, souvent la partie utile.
        """
        if not isinstance(saisie, dict):
            raise ValueError("Un retour est un objet JSON.")
        try:
            avis = Avis(saisie.get("avis"))
        except ValueError:
            raise ChampInvalide("avis", "avis : « utile » ou « pas_utile » est attendu.") from None
        commentaire = saisie.get("commentaire")
        if commentaire is None:
            commentaire = ""
        if not isinstance(commentaire, str):
            raise ChampInvalide("commentaire", "commentaire : un texte est attendu.")
        # Les fins de ligne d'un formulaire arrivent en CRLF : ramenées à `\n` avant de
        # compter, pour qu'une ligne coûte un caractère ici comme sur le site.
        commentaire = commentaire.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(commentaire) > LONGUEUR_MAX_COMMENTAIRE:
            raise ChampInvalide(
                "commentaire",
                f"commentaire : {LONGUEUR_MAX_COMMENTAIRE} caractères au plus "
                f"({len(commentaire)} reçus).",
            )
        return cls(profil_id=profil_id, jour=jour, avis=avis, commentaire=commentaire)

    def en_json(self) -> dict:
        return {
            "username": self.username,
            "jour": self.jour.isoformat(),
            "avis": self.avis.value,
            "commentaire": self.commentaire,
            "vote_le": self.vote_le,
        }


class LienRetour:
    """Le jeton de vote d'une journée, ses deux liens, et sa relecture.

    Pas d'expiration : une lettre lue en retard mérite encore son avis. Le jeton ne porte
    que l'identifiant du profil et la date, et l'API refuse celui d'un profil disparu.
    """

    def __init__(self, signataire: Signataire):
        self._signataire = signataire

    def jeton(self, profil_id: str, jour: dt.date) -> str:
        """Déterministe : même profil, même journée, même jeton — `--send-only` reste fidèle."""
        return self._signataire.signer(VERSION, profil_id, jour.isoformat())

    @staticmethod
    def lien(site_url: str, jeton: str, avis: Avis) -> str:
        return f"{site_url.rstrip('/')}/retour/{jeton}?avis={avis.value}"

    def lire(self, jeton: str) -> JourneeVisee:
        """La journée que vise le jeton. Altéré, d'une autre clé, d'un autre format ou d'une
        date impossible : `JetonInvalide`."""
        # Importé ici : `sorties` compose les journées par `newsletter`, qui importe ce
        # module pour ses liens de vote — en tête de fichier, l'import serait circulaire.
        from rssresume.api.sorties import date_valide

        champs = self._signataire.verifier(jeton)
        if len(champs) != 3 or champs[0] != VERSION:
            raise JetonInvalide("Format de jeton inconnu.")
        _, profil_id, texte = champs
        jour = date_valide(texte)
        if jour is None:
            raise JetonInvalide("Date de jeton invalide.")
        return JourneeVisee(profil_id, jour)
