"""La tournée : la même journée digérée pour chaque profil, puis marquée lue une fois.

Plusieurs personnes lisent le même FreshRSS, et l'état « lu » y est unique. Le marquage
comme lu ne peut donc plus appartenir au digest d'une personne : le premier profil servi
viderait la journée de tous les suivants, puisque l'API écarte les articles lus. Chaque
digest tourne ici sans marquer, et la tournée marque à la fin — et seulement quand tout le
monde a été servi.

Ce module ne choisit aucun fournisseur : il reçoit de quoi assembler un digest
(`cli.build_service`), qui reste le seul endroit où ils sont choisis.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

from rssresume import runlog
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.models import Article
from rssresume.profil import Annuaire
from rssresume.tools import console

#: Assemble le digest d'une personne autour du client FreshRSS partagé par la tournée.
Assembleur = Callable[[AppConfig, FreshRSSClient], DigestService]


class Tournee:
    """Sert une journée à chaque personne de l'annuaire, l'échec de l'une isolé des autres.

    `config` est celle de l'installation ; `Annuaire` dit qui servir et lit chaque
    profil ; le client FreshRSS est partagé pour que les catégories et les articles ne
    soient lus qu'une fois, quel que soit le nombre de profils.
    """

    def __init__(
        self,
        config: AppConfig,
        annuaire: Annuaire,
        freshrss_client: FreshRSSClient,
        assembleur: Assembleur,
    ):
        self._config = config
        self._annuaire = annuaire
        self._freshrss_client = freshrss_client
        self._assembleur = assembleur

    def run(
        self,
        day: dt.date,
        username: str | None = None,
        send_email: bool = True,
        write_tags: bool = True,
        mark_read: bool = True,
    ) -> list[str]:
        """Sert `day` à tous les profils, ou au seul `username`. Rend les noms en échec.

        Un profil qui échoue — document fautif, fournisseur en panne — est journalisé,
        et les suivants sont servis : même arbitrage que la boucle des jours, où un matin
        perdu ne coûte pas les suivants.
        """
        cibles = self._annuaire.cibles(username)
        if not cibles:
            console.log("Tournée : aucun profil à servir")
            return []

        console.log(f"Tournée du {day.isoformat()} : {', '.join(cibles)}")
        lus: list[Article] = []
        echecs: list[str] = []
        for nom in cibles:
            try:
                lus.extend(self._servir(nom, day, send_email, write_tags))
            except Exception as exc:  # noqa: BLE001 — un profil perdu, pas tous les suivants
                console.error(f"Échec du digest de « {nom} » du {day.isoformat()} : {exc!r}")
                echecs.append(nom)

        if not mark_read:
            console.log("Marquage comme lu : ignoré (--no-mark-read)")
        elif self._peut_marquer(cibles, echecs):
            self._marquer(lus)
        return echecs

    def _servir(self, nom: str, day: dt.date, send_email: bool, write_tags: bool) -> list[Article]:
        """Le digest d'une personne, sans marquage : rend ce qu'il a lu."""
        config = self._config.pour(self._annuaire.lecteur(nom))
        service = self._assembleur(config, self._freshrss_client)
        digests = service.run(day, send_email=send_email, write_tags=write_tags, mark_read=False)
        if config.debug:
            # Relecture du répertoire de sortie, comme `--journal` : ce qu'on lit dans
            # les logs du matin est ce que la commande rejouera le soir.
            console.log(runlog.lire_bilan(config.output_dir / day.isoformat(), day).texte(detail=True))
        return [article for digest in digests for article in digest.articles]

    def _peut_marquer(self, cibles: list[str], echecs: list[str]) -> bool:
        """Vrai seulement quand chaque profil de l'annuaire vient d'être servi.

        Un profil en échec doit pouvoir être rejoué sans `--include-read` : ses articles
        restent non lus. Un passage ciblé (`--profil`) ne marque pas non plus quand
        d'autres profils existent — ils n'ont peut-être pas encore eu leur journée. Les
        articles restés non lus ne reviennent dans aucun autre jour : la lecture est
        bornée à la journée, ils ne coûtent qu'un compteur dans FreshRSS.
        """
        if echecs:
            console.log(
                f"Marquage comme lu : différé, {len(echecs)} profil(s) en échec "
                f"({', '.join(echecs)}) doivent pouvoir rejouer la journée"
            )
            return False
        if set(cibles) != set(self._annuaire.usernames()):
            console.log("Marquage comme lu : différé, d'autres profils n'ont pas été servis")
            return False
        return True

    def _marquer(self, articles: list[Article]) -> None:
        """Marque une fois chaque article lu par la tournée, quel que soit le nombre de lecteurs."""
        uniques = list({article.item_id: article for article in articles}.values())
        if uniques:
            self._freshrss_client.mark_as_read(uniques)
