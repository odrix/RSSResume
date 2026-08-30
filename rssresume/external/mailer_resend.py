"""Envoi du digest par l'API HTTPS de Resend, quand le SMTP ne sort pas.

Un hébergeur qui filtre 25, 465 et 587 en sortie — la règle plutôt que l'exception sur
les VPS — rend `mailer.EmailSender` inutilisable sans que rien dans la configuration ne
soit fautif : la connexion meurt sur un `TimeoutError` avant d'avoir dit un mot. Le 443,
lui, sort forcément, puisque c'est déjà par là que passent FreshRSS et les fournisseurs
de LLM. Ce module envoie donc le même digest par le même chemin qu'eux.

Le contrat est celui de `mailer.EmailSender`, à la lettre : `DigestService` ne voit qu'un
`EmailSenderProtocol` et n'a pas à savoir lequel des deux il tient.

Resend n'accepte d'expéditeur que sur un domaine vérifié chez lui — vérification qui
passe par des enregistrements DNS, donc par un domaine qui résout. Le compte de test
`onboarding@resend.dev` fait exception, mais n'écrit qu'au propriétaire du compte.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import pathlib
import urllib.error
import urllib.request
from typing import Iterable

from rssresume.config import AppConfig
from rssresume.tools import console, http

DEFAULT_MIME_TYPE = "application/octet-stream"

API_URL = "https://api.resend.com/emails"

#: Plafond de Resend, pièces jointes encodées comprises. Vérifié avant l'appel : un POST
#: de quarante mégaoctets qu'on laisserait partir pour se faire refuser coûte la montée
#: entière, et rend un 413 nu là où le compte des mp3 explique tout.
MAX_PAYLOAD_BYTES = 40 * 1024 * 1024


class ResendEmailSender:
    """Le même envoi que `EmailSender`, par l'API plutôt que par le port 465."""

    def __init__(self, config: AppConfig):
        self._config = config

    def is_configured(self) -> bool:
        return bool(
            self._config.resend_api_key and self._config.smtp_from and self._config.smtp_to
        )

    def send(self, subject: str, body: str, attachments: Iterable[pathlib.Path]) -> None:
        if not self.is_configured():
            raise RuntimeError("Resend configuration is incomplete.")

        attachments = list(attachments)
        destinataires = ", ".join(self._config.smtp_to)
        console.log(
            f"Email : envoi à {destinataires} via Resend "
            f"({len(attachments)} pièce(s) jointe(s))"
        )
        identifiant = self._post(self._payload(subject, body, attachments))
        console.log(f"Email : envoyé{f' ({identifiant})' if identifiant else ''}")

    def _payload(self, subject: str, body: str, attachments: list[pathlib.Path]) -> dict:
        """Le message tel que Resend l'attend, pièces jointes en base64.

        Pas de `Date` ni de `Message-ID` à poser ici, contrairement au SMTP : c'est
        Resend qui compose le message final et les ajoute.
        """
        payload = {
            "from": self._config.smtp_from,
            "to": list(self._config.smtp_to),
            "subject": subject,
            "text": body,
        }
        if attachments:
            payload["attachments"] = [self._attachment(chemin) for chemin in attachments]
        return payload

    @staticmethod
    def _attachment(chemin: pathlib.Path) -> dict:
        mime_type, _ = mimetypes.guess_type(str(chemin))
        return {
            "filename": chemin.name,
            "content": base64.b64encode(chemin.read_bytes()).decode(),
            "content_type": mime_type or DEFAULT_MIME_TYPE,
        }

    def _post(self, payload: dict) -> str | None:
        """POST le message, et rend l'identifiant que Resend lui donne.

        Rejoué sur un échec passager, comme tout ce qui sort de la machine : le détail
        est dans `tools/http.py`.
        """
        corps = json.dumps(payload).encode()
        if len(corps) > MAX_PAYLOAD_BYTES:
            raise RuntimeError(
                f"Resend : message de {len(corps) // 1024 // 1024} Mo, au-dessus du plafond "
                f"de {MAX_PAYLOAD_BYTES // 1024 // 1024} Mo. Les pièces jointes encodées "
                "pèsent un tiers de plus que les fichiers."
            )
        request = urllib.request.Request(
            API_URL,
            data=corps,
            headers={
                "Authorization": f"Bearer {self._config.resend_api_key}",
                "Content-Type": "application/json",
            },
        )

        def _envoyer() -> bytes:
            with urllib.request.urlopen(request) as response:
                return response.read()

        try:
            reponse = http.retry(_envoyer, "Resend")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Resend : {exc.code} {detail}") from exc
        return self._identifiant(reponse)

    @staticmethod
    def _identifiant(reponse: bytes) -> str | None:
        """L'`id` du message, s'il est lisible. Une réponse opaque n'est pas un échec."""
        try:
            return json.loads(reponse or b"{}").get("id")
        except (ValueError, AttributeError):
            return None
