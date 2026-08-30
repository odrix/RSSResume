"""Le choix du transport : le port 465, ou le 443 de Resend.

Deux implémentations du même contrat, et une table qui les nomme. Le reste du code ne
voit qu'un `EmailSenderProtocol` : ni `DigestService` ni `cli` n'ont à savoir par où
part le digest, et brancher un troisième transport un jour ne les touchera pas.

    sender(config).send(sujet, corps, [audio])
"""

from __future__ import annotations

from rssresume.config import MAIL_TRANSPORT_RESEND, MAIL_TRANSPORT_SMTP, AppConfig
from rssresume.external.mailer import EmailSender
from rssresume.external.mailer_resend import ResendEmailSender
from rssresume.protocols import EmailSenderProtocol

#: Le nom lu dans l'environnement, et ce qu'il construit. Les noms eux-mêmes vivent dans
#: `config`, qui les valide au lancement : ici, la table ne peut plus recevoir d'inconnu.
TRANSPORTS = {
    MAIL_TRANSPORT_SMTP: EmailSender,
    MAIL_TRANSPORT_RESEND: ResendEmailSender,
}


def sender(config: AppConfig) -> EmailSenderProtocol:
    """L'expéditeur que la configuration désigne."""
    return TRANSPORTS[config.mail_transport](config)
