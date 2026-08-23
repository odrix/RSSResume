"""Envoi de l'email quotidien avec les fichiers audio en pièces jointes."""

from __future__ import annotations

import email.message
import mimetypes
import pathlib
import smtplib
from typing import Iterable

from rssresume import console
from rssresume.config import AppConfig

DEFAULT_MIME_TYPE = "application/octet-stream"


class EmailSender:
    def __init__(self, config: AppConfig):
        self._config = config

    def is_configured(self) -> bool:
        return bool(self._config.smtp_host and self._config.smtp_from and self._config.smtp_to)

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        if not self.is_configured():
            raise RuntimeError("SMTP configuration is incomplete.")

        attachments = list(attachments)
        recipients = ", ".join(self._config.smtp_to)
        console.log(
            f"Email : envoi à {recipients} via {self._config.smtp_host}:{self._config.smtp_port} "
            f"({len(attachments)} pièce(s) jointe(s))"
        )
        message = self._build_message(subject, body, attachments)
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
    ) -> email.message.EmailMessage:
        message = email.message.EmailMessage()
        message["Subject"] = subject
        message["From"] = self._config.smtp_from
        message["To"] = ", ".join(self._config.smtp_to)
        message.set_content(body)

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

    def _connect(self) -> smtplib.SMTP:
        if self._config.smtp_use_ssl:
            return smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port)
        return smtplib.SMTP(self._config.smtp_host, self._config.smtp_port)
