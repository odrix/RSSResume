"""Envoi de l'email quotidien avec les fichiers audio en pièces jointes."""

from __future__ import annotations

import email.message
import email.utils
import mimetypes
import pathlib
import smtplib
from typing import Iterable

from rssresume.config import AppConfig
from rssresume.tools import console

DEFAULT_MIME_TYPE = "application/octet-stream"

#: Délai d'ouverture de la connexion SMTP. Sans lui, `smtplib` laisse le noyau décider :
#: un port sortant filtré — ce que font par défaut beaucoup d'hébergeurs sur 25, 465 et
#: 587 — ne se voit qu'au bout de deux minutes d'attente muette, et sous la forme d'un
#: `TimeoutError(110)` qui ne dit pas d'où il vient. Trente secondes suffisent à un
#: serveur qui répond, et rendent la panne lisible tout de suite.
CONNECT_TIMEOUT = 30


class EmailSender:
    def __init__(self, config: AppConfig):
        self._config = config

    def is_configured(self) -> bool:
        return bool(self._config.smtp_host and self._config.smtp_from and self._config.smtp_to)

    def send(
        self,
        subject: str,
        body: str,
        attachments: Iterable[pathlib.Path],
        html: str | None = None,
    ) -> None:
        if not self.is_configured():
            raise RuntimeError("SMTP configuration is incomplete.")

        attachments = list(attachments)
        recipients = ", ".join(self._config.smtp_to)
        console.log(
            f"Email : envoi à {recipients} via {self._config.smtp_host}:{self._config.smtp_port} "
            f"({len(attachments)} pièce(s) jointe(s))"
        )
        message = self._build_message(subject, body, attachments, html)
        with self._connect() as smtp:
            if self._config.smtp_use_tls and not self._config.smtp_use_ssl:
                smtp.starttls()
            if self._config.smtp_username and self._config.smtp_password:
                smtp.login(self._config.smtp_username, self._config.smtp_password)
            smtp.send_message(message)
        console.log("Email : envoyé")

    def _build_message(
        self,
        subject: str,
        body: str,
        attachments: Iterable[pathlib.Path],
        html: str | None = None,
    ) -> email.message.EmailMessage:
        message = email.message.EmailMessage()
        message["Subject"] = subject
        message["From"] = self._config.smtp_from
        message["To"] = ", ".join(self._config.smtp_to)
        # `EmailMessage` ne pose ni `Date` ni `Message-ID`, et `send_message` non plus :
        # un message parti sans eux est un message que la RFC 5322 dit incomplet. Certains
        # relais les ajoutent, d'autres non — et un message sans eux arrive chez les gros
        # fournisseurs dans les indésirables, quand il n'est pas refusé. Deux en-têtes
        # posés ici valent mieux qu'un digest silencieusement classé.
        message["Date"] = email.utils.formatdate(localtime=True)
        message["Message-ID"] = email.utils.make_msgid(domain=self._domaine_expediteur())
        message.set_content(body)
        if html:
            # Le texte d'abord, le HTML ensuite : `add_alternative` construit un
            # `multipart/alternative` dont la DERNIÈRE partie est celle que le client
            # préfère. Dans l'ordre inverse, tout le monde recevrait le texte brut.
            message.add_alternative(html, subtype="html")

        for attachment in attachments:
            mime_type, _ = mimetypes.guess_type(str(attachment))
            maintype, subtype = (mime_type or DEFAULT_MIME_TYPE).split("/", 1)
            message.add_attachment(
                attachment.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment.name,
            )
        return message

    def _domaine_expediteur(self) -> str | None:
        """Le domaine de l'expéditeur, pour que le `Message-ID` en porte la marque.

        `None` si l'adresse est illisible : `make_msgid` retombe alors sur le nom de la
        machine, ce qui reste un identifiant valide.
        """
        _, adresse = email.utils.parseaddr(self._config.smtp_from or "")
        _, _, domaine = adresse.rpartition("@")
        return domaine or None

    def _connect(self) -> smtplib.SMTP:
        if self._config.smtp_use_ssl:
            return smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port, timeout=CONNECT_TIMEOUT)
        return smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=CONNECT_TIMEOUT)
