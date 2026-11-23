"""Le lien de désabonnement de la lettre : un jeton signé, vérifiable sans session.

Qui reçoit la lettre n'a pas forcément de compte sur le site — un destinataire ajouté
par quelqu'un d'autre n'en a jamais —, et Gmail comme Yahoo exigent d'un expéditeur en
volume un désabonnement en un clic, sans connexion. Le lien porte donc lui-même son
autorisation : une signature que seuls le travailleur et l'API savent produire, avec le
secret qu'ils partagent déjà (`RSSRESUME_API_TOKEN`). Le site ne voit jamais la clé, il
relaie le jeton.

Signé plutôt que stocké : le jeton se recalcule à l'identique à chaque composition, et
`--send-only` rend donc la même lettre que le passage du jour sans rien écrire nulle part.
Il ne « sert qu'une fois » sans table de jetons : il porte les empreintes des adresses à
qui la lettre est partie, et une fois les destinataires vidés, aucune ne correspond plus.
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

#: Octets gardés d'une empreinte, par défaut.
LONGUEUR_EMPREINTE = 16

#: Octets gardés de l'empreinte d'UNE adresse : six, soit huit caractères base64url, sans
#: remplissage. L'empreinte n'a pas à résister à une recherche — elle est à clé, et qui ne
#: tient pas la clé ne peut en calculer aucune —, seulement à ne pas confondre par hasard
#: une adresse ajoutée après l'envoi avec l'une de celles de la lettre : une chance sur
#: 2^48 par paire, quand une liste en compte quelques-unes. Courte parce qu'il y en a une
#: par destinataire, et que le lien doit rester un lien.
OCTETS_EMPREINTE_ADRESSE = 6
LONGUEUR_EMPREINTE_ADRESSE = 8

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
    """Un jeton vérifié : le profil qu'il vise, et les adresses auxquelles la lettre est partie.

    Elle ne dit pas d'elle-même si elle s'applique encore : seul l'état des destinataires
    au moment de l'écriture le dit, d'où `concerne`, appelé sous le verrou d'écriture.
    """

    def __init__(self, profil_id: str, empreintes: frozenset[str], desabonnement: "Desabonnement"):
        self.profil_id = profil_id
        self._empreintes = empreintes
        self._desabonnement = desabonnement

    def concerne(self, emails) -> bool:
        """Vrai si l'une des adresses actuelles est l'une de celles à qui la lettre est partie.

        Une seule suffit, et non la liste entière : la liste vit après l'envoi — une
        invitation confirmée, une adresse retirée —, et exiger qu'elle soit restée
        identique rendait caducs les liens de toutes les lettres déjà parties. Le
        destinataire qui cliquait alors « Se désabonner » lisait « déjà utilisé », et
        finissait par signaler la lettre comme indésirable.

        Faux pour une liste vide ou sans aucune adresse de la lettre : c'est ce qui fait
        qu'un lien ne sert qu'une fois — les destinataires retirés, il n'y a plus rien à
        désabonner.
        """
        actuelles = {self._desabonnement.empreinte(adresse) for adresse in emails}
        return any(
            hmac.compare_digest(actuelle, empreinte)
            for actuelle in actuelles
            for empreinte in self._empreintes
        )


class Desabonnement:
    """Le jeton de désabonnement d'un profil, son lien, et sa relecture.

    Le jeton porte l'identifiant du profil — stable, contrairement au nom qu'on pourrait
    un jour changer — et une empreinte courte de chaque adresse à qui la lettre est partie,
    triées et mises bout à bout. Sans état côté serveur, ce sont elles qui lient le lien à
    ses destinataires : tant que l'une d'elles reçoit encore la lettre, il vaut ; quand il
    n'en reste aucune, il est refusé.
    """

    def __init__(self, signataire: Signataire):
        self._signataire = signataire

    def empreinte(self, adresse: str) -> str:
        """L'empreinte d'une adresse, insensible à la casse et aux blancs de bord.

        Une majuscule tapée autrement ne change pas qui reçoit la lettre : le lien doit
        rester valable.
        """
        return self._signataire.empreinte(adresse.strip().lower(), OCTETS_EMPREINTE_ADRESSE)

    def jeton(self, profil_id: str, emails) -> str:
        """Le jeton du profil pour ces destinataires. Déterministe : même profil, mêmes
        adresses, même jeton — c'est ce qui garde `--send-only` fidèle.

        Les empreintes sont triées, dédoublonnées et concaténées : de longueur fixe, elles
        se redécoupent sans séparateur, et l'alphabet d'URL n'en a pas de libre — `-` et `_`
        appartiennent au base64url, le point sépare les champs signés.
        """
        empreintes = "".join(sorted({self.empreinte(adresse) for adresse in emails}))
        if not empreintes:
            raise ValueError("Désabonnement : un jeton exige au moins un destinataire.")
        return self._signataire.signer(VERSION, profil_id, empreintes)

    @staticmethod
    def lien(site_url: str, jeton: str) -> str:
        return f"{site_url.rstrip('/')}/desabonnement/{jeton}"

    def lire(self, jeton: str) -> Demande:
        """La demande que porte un jeton. Altéré, d'une autre clé ou d'un autre format :
        `JetonInvalide`."""
        champs = self._signataire.verifier(jeton)
        if len(champs) != 3 or champs[0] != VERSION or len(champs[2]) % LONGUEUR_EMPREINTE_ADRESSE:
            raise JetonInvalide("Format de jeton inconnu.")
        _, profil_id, bout_a_bout = champs
        empreintes = frozenset(
            bout_a_bout[debut : debut + LONGUEUR_EMPREINTE_ADRESSE]
            for debut in range(0, len(bout_a_bout), LONGUEUR_EMPREINTE_ADRESSE)
        )
        return Demande(profil_id, empreintes, self)
