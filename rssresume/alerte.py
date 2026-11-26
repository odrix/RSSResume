"""L'alerte à l'exploitant quand la tournée a échoué pour au moins un profil.

Un profil en échec n'était dit que dans les logs du conteneur : l'inscrit s'en
apercevrait le premier, en ne recevant rien. En fin de tournée, s'il y a eu des
échecs, un seul email part au transport déjà configuré, qui nomme chaque profil,
cause résumée, et la commande `--journal` à lancer pour chacun, savoir avant
l'inscrit qu'il n'a rien reçu.

Le destinataire est un réglage de l'installation (`config.admin_email`) :
qui avertir n'est pas une donnée de la personne servie.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from rssresume.config import AppConfig
from rssresume.external import mail
from rssresume.models import EchecProfil
from rssresume.protocols import EmailSenderProtocol
from rssresume.tools import console

#: La cause tenue en une ligne : un repr tronqué dit le type et le message levés.
#: Plus long, l'email embarquerait une pile que personne ne lit, le journal, lui,
#: garde les détails.
PLAFOND_CAUSE = 200

#: L'exception qui traverse la tournée peut porter un message en plusieurs lignes -
#: un traceback, un JSON d'API. Une cause multiligne casserait la ligne du profil
#: dans le corps de l'alerte ; chaque retour à la ligne est rastérisé.
SEPARATEUR_LIGNE = " / "


def resumer_cause(exc: BaseException) -> str:
    """Ce que l'exception dit d'elle-même, en une seule ligne d'au plus `PLAFOND_CAUSE`."""
    cause = repr(exc).replace("\n", SEPARATEUR_LIGNE)
    if len(cause) > PLAFOND_CAUSE:
        cause = cause[: PLAFOND_CAUSE - 3] + "..."
    return cause


class AlerteEchecs:
    """Un seul email à l'exploitant par tournée en échec, par le transport du digest.

    L'expéditeur, lui, est construit sur la configuration dérivée, la même, à
    l'exception des destinataires, qui sont l'adresse de l'exploitant. La vérifier
    avant d'envoyer (`is_configured`), c'est ce qui garde le comportement d'une
    installation sans courrier inchangé : les logs seulement.
    """

    def __init__(self, expediteur: EmailSenderProtocol):
        self._expediteur = expediteur

    @classmethod
    def depuis_config(cls, config: AppConfig) -> "AlerteEchecs":
        """L'alerte que `config` institue : le transport du digest, l'adresse de l'exploitant.

        Le transport est celui déjà configuré, SMTP ou Resend, même appel, même
        expéditeur `SMTP_FROM`, construit sur la configuration dérivée, aux seuls
        destinataires changés : l'adresse de l'exploitant, réglage de l'installation,
        vit dans la configuration et n'a pas besoin d'aller nulle part ailleurs.
        `config.admin_email` doit être renseigné ; `cli.main` ne construit pas
        l'alerte dans le cas contraire, et ne l'invoque jamais comme collaborateur.
        """
        return cls(
            expediteur=mail.sender(dataclasses.replace(config, smtp_to=[config.admin_email])),
        )

    def notifier(self, day: dt.date, echecs: list[EchecProfil]) -> None:
        """Écrit une fois à l'exploitant : nom, cause et rejeu de chaque profil.

        Texte seul, sans pièce jointe ni HTML : ce message dit une panne, il n'a
        rien à montrer. Un transport non configuré est un silence assumé, le jour
        de l'installation où l'on n'envoie pas, l'alerte ne doit pas faire échouer
        la tournée qui vient pourtant de finir.
        """
        if not echecs:
            return
        jour = day.isoformat()
        lignes = [
            f"- {echec.nom}, {echec.cause}\n"
            f"  Rejouer et diagnostiquer : python -m rssresume --journal --date {jour} "
            f"--profil {echec.nom}"
            for echec in echecs
        ]
        sujet = f"Tournée du {jour} : {len(echecs)} profil(s) en échec"
        corps = (
            f"La tournée du {jour} a échoué pour {len(echecs)} profil(s) ci-dessous ; "
            "rien n'a été marqué comme lu, ils pourront rejouer leur journée.\n\n"
            + "\n".join(lignes)
        )
        if not self._expediteur.is_configured():
            console.error(
                "Alerte à l'exploitant : transport non configuré, rien n'est envoyé, "
                f"{len(echecs)} profil(s) en échec : {', '.join(e.nom for e in echecs)}"
            )
            return
        self._expediteur.send(sujet, corps, [])
