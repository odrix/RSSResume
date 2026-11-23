"""Le lien de désabonnement de la lettre : un jeton signé, vérifiable sans session.

Qui reçoit la lettre n'a pas forcément de compte sur le site — un destinataire ajouté
par quelqu'un d'autre n'en a jamais —, et Gmail comme Yahoo exigent d'un expéditeur en
volume un désabonnement en un clic, sans connexion. Le lien porte donc lui-même son
autorisation : une signature que seuls le travailleur et l'API savent produire, avec le
secret qu'ils partagent déjà (`RSSRESUME_API_TOKEN`). Le site ne voit jamais la clé, il
relaie le jeton.

Signé plutôt que stocké : le jeton se recalcule à l'identique à chaque composition, et
`--send-only` rend donc la même lettre que le passage du jour sans rien écrire nulle part.
Il ne « sert qu'une fois » sans table de jetons : il est lié à l'état des destinataires,
et une fois ceux-ci vidés, l'empreinte qu'il porte ne correspond plus à rien.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

#: La valeur de l'en-tête `List-Unsubscribe-Post` (RFC 8058), la même pour tous : c'est
#: elle qui dit au client mail que le POST sur l'URL suffit, sans page à afficher.
LIST_UNSUBSCRIBE_POST = "List-Unsubscribe=One-Click"

#: L'usage de la clé : une clé par usage, pour qu'une signature valable ici ne le soit
#: jamais pour un autre lien signé avec le même secret.
OBJET_DESABONNEMENT = "desabonnement"

#: La version du format, signée avec le reste : un format changé ne relira jamais par
#: erreur un ancien jeton comme un nouveau.
VERSION = "v1"

#: Octets gardés de l'empreinte des destinataires. Seize suffisent à ce qu'aucune autre
#: liste ne la reproduise par hasard, et gardent le lien court.
LONGUEUR_EMPREINTE = 16

#: Ce qu'un champ signé peut contenir : de quoi se poser dans un chemin d'URL tel quel,
#: sans échappement, et sans jamais contenir le point qui sépare les champs.
_CHAMP = re.compile(r"[A-Za-z0-9_-]+")


class JetonInvalide(ValueError):
    """Un jeton illisible, altéré, ou signé avec une autre clé.

    Une seule classe pour tous ces cas : qui présente un jeton n'a pas à apprendre
    pourquoi il est refusé, seulement qu'il l'est.
    """


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


class Signataire:
    """Signe et vérifie une suite de champs, avec une clé propre à un usage.

    Générique exprès : le désabonnement est le premier lien signé de la lettre, pas le
    dernier. La clé de chaque usage est dérivée du secret et de l'`objet`, si bien qu'un
    jeton détourné d'un usage vers un autre n'y est qu'une chaîne fausse.
    """

    def __init__(self, secret: str, objet: str):
        if not secret:
            raise ValueError("Signataire : un secret non vide est exigé.")
        self._cle = hmac.new(
            secret.encode("utf-8"), b"rssresume:" + objet.encode("utf-8"), hashlib.sha256
        ).digest()

    def signer(self, *champs: str) -> str:
        """`champ.champ….signature`. Un champ hors de l'alphabet d'URL : `ValueError`.

        Les champs restent lisibles plutôt qu'encodés : ils ne portent rien de secret, et
        un jeton qu'on peut lire à l'œil se diagnostique sans outil.
        """
        if not champs:
            raise ValueError("Signataire : rien à signer.")
        for champ in champs:
            if not _CHAMP.fullmatch(champ):
                raise ValueError(f"Signataire : champ « {champ} » hors de l'alphabet d'URL.")
        corps = ".".join(champs)
        return f"{corps}.{self._signature(corps)}"

    def verifier(self, jeton: str) -> list[str]:
        """Les champs signés, ou `JetonInvalide`. Comparaison à temps constant."""
        if not isinstance(jeton, str):
            raise JetonInvalide("Jeton illisible.")
        corps, _, signature = jeton.rpartition(".")
        champs = corps.split(".")
        if not corps or not all(_CHAMP.fullmatch(champ) for champ in champs):
            raise JetonInvalide("Jeton illisible.")
        attendue = self._signature(corps).encode("ascii")
        if not hmac.compare_digest(signature.encode("ascii", "replace"), attendue):
            raise JetonInvalide("Signature invalide.")
        return champs

    def empreinte(self, texte: str, longueur: int = LONGUEUR_EMPREINTE) -> str:
        """Une empreinte à clé de `texte`, tronquée.

        À clé et non un simple hachage : l'empreinte voyage en clair dans le lien, et un
        hachage nu permettrait à qui tient le lien de vérifier hors ligne qu'une adresse
        devinée en fait partie.
        """
        condensat = hmac.new(self._cle, b"empreinte:" + texte.encode("utf-8"), hashlib.sha256)
        return _b64(condensat.digest()[:longueur])

    def _signature(self, corps: str) -> str:
        return _b64(hmac.new(self._cle, corps.encode("ascii"), hashlib.sha256).digest())


class Demande:
    """Un jeton vérifié : le profil qu'il vise, et les destinataires qu'il désigne.

    Elle ne dit pas d'elle-même si elle s'applique encore : seul l'état des destinataires
    au moment de l'écriture le dit, d'où `concerne`, appelé sous le verrou d'écriture.
    """

    def __init__(self, profil_id: str, empreinte: str, desabonnement: "Desabonnement"):
        self.profil_id = profil_id
        self._empreinte = empreinte
        self._desabonnement = desabonnement

    def concerne(self, emails: list[str] | tuple[str, ...]) -> bool:
        """Vrai si `emails` sont les destinataires pour lesquels le lien a été émis.

        Faux pour une liste vide : c'est ce qui fait qu'un lien ne sert qu'une fois — une
        fois les destinataires retirés, il n'y a plus rien à désabonner.
        """
        if not emails:
            return False
        return hmac.compare_digest(self._empreinte, self._desabonnement.empreinte(emails))


class Desabonnement:
    """Le jeton de désabonnement d'un profil, son lien, et sa relecture.

    Le jeton porte l'identifiant du profil — stable, contrairement au nom qu'on pourrait
    un jour changer — et une empreinte de ses destinataires. Sans état côté serveur, c'est
    cette empreinte qui lie le lien à une liste précise : vidée ou changée, la liste ne
    correspond plus, et le lien est refusé.
    """

    def __init__(self, signataire: Signataire):
        self._signataire = signataire

    def empreinte(self, emails) -> str:
        """L'empreinte des destinataires, insensible à la casse et à l'ordre.

        Le document normalise déjà les adresses, mais une liste réordonnée par le site ou
        une majuscule tapée autrement ne change pas qui reçoit la lettre : le lien doit
        rester valable.
        """
        adresses = sorted({adresse.strip().lower() for adresse in emails})
        return self._signataire.empreinte("\n".join(adresses))

    def jeton(self, profil_id: str, emails) -> str:
        return self._signataire.signer(VERSION, profil_id, self.empreinte(emails))

    @staticmethod
    def lien(site_url: str, jeton: str) -> str:
        return f"{site_url.rstrip('/')}/desabonnement/{jeton}"

    def lire(self, jeton: str) -> Demande:
        """La demande que porte un jeton. Altéré, d'une autre clé ou d'un autre format :
        `JetonInvalide`."""
        champs = self._signataire.verifier(jeton)
        if len(champs) != 3 or champs[0] != VERSION:
            raise JetonInvalide("Format de jeton inconnu.")
        _, profil_id, empreinte = champs
        return Demande(profil_id, empreinte, self)
