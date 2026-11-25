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

import dataclasses
import datetime as dt
from typing import Callable

from rssresume import runlog
from rssresume.alerte import resumer_cause
from rssresume.categories import Catalogue
from rssresume.config import AppConfig
from rssresume.digest import DigestService
from rssresume.external.freshrss import FreshRSSClient
from rssresume.models import Article, EchecProfil
from rssresume.protocols import AlerteEchecsProtocol
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
        alerte: AlerteEchecsProtocol | None = None,
    ):
        self._config = config
        self._annuaire = annuaire
        self._freshrss_client = freshrss_client
        self._assembleur = assembleur
        #: Construit par `cli.main` quand l'installation a une adresse d'exploitant et
        #: que la tournée enverra du courrier ; absent, le comportement ne change pas.
        self._alerte = alerte

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
        # Avant toute lecture : une ligne du catalogue corrompue, ou un catalogue absent
        # pour plusieurs personnes, arrêtent la tournée avant qu'elle ne serve quiconque.
        installation = dataclasses.replace(self._config, catalogue=self._annuaire.catalogue())
        self._verifier_catalogue(installation.catalogue)

        cibles = self._annuaire.cibles(username)
        if not cibles:
            console.log("Tournée : aucun profil à servir")
            return []

        console.log(f"Tournée du {day.isoformat()} : {', '.join(cibles)}")
        lus: list[Article] = []
        echecs: list[EchecProfil] = []
        for nom in cibles:
            try:
                lus.extend(self._servir(installation, nom, day, send_email, write_tags))
            except Exception as exc:  # noqa: BLE001 — un profil perdu, pas tous les suivants
                console.error(f"Échec du digest de « {nom} » du {day.isoformat()} : {exc!r}")
                echecs.append(EchecProfil(nom, resumer_cause(exc)))

        noms_en_echec = [echec.nom for echec in echecs]
        if not mark_read:
            console.log("Marquage comme lu : ignoré (--no-mark-read)")
        elif self._peut_marquer(cibles, noms_en_echec):
            lus.extend(self._articles_orphelins(installation, day))
            self._marquer(lus)
        if echecs and self._alerte is not None:
            # Dernier geste de la tournée, enveloppé : une alerte qu'on n'arrive pas à
            # envoyer ne doit rien changer à ce qui a déjà été servi et marqué, ni au
            # rendu des échecs. L'inscrit apprendra sa panne autrement.
            try:
                self._alerte.notifier(day, echecs)
            except Exception as exc:  # noqa: BLE001 — l'alerte ne coûte pas la tournée
                console.error(f"Alerte à l'exploitant impossible ({exc!r}) ; la tournée est finie")
        return noms_en_echec

    def _verifier_catalogue(self, catalogue: Catalogue) -> None:
        """Un catalogue ouvert ne vaut que pour une seule personne.

        Ouvert, il sert tout à tout le monde : pour une installation à une personne, c'est
        le comportement d'avant le catalogue, et il reste permis — avec un avertissement à
        chaque tournée, pour qu'il ne s'oublie pas. Dès deux personnes, la veille privée de
        l'une partirait chez l'autre : la tournée refuse de démarrer, et dit quoi faire.
        """
        if not catalogue.ouvert:
            return
        usernames = self._annuaire.usernames()
        if len(usernames) > 1:
            raise ValueError(
                f"Aucun catalogue des catégories pour {len(usernames)} profils "
                f"({', '.join(usernames)}) : chacun recevrait toutes les catégories du FreshRSS, "
                f"veille privée comprise. {self._annuaire.remede_sans_catalogue()}"
            )
        if usernames:
            console.log(
                "Catalogue des catégories : aucun — toutes les catégories sont servies au seul "
                f"profil. Avant d'en ajouter un second : {self._annuaire.remede_sans_catalogue()}"
            )

    def _orphelines(self, installation: AppConfig) -> list[str]:
        """Les catégories de l'installation que personne ne reçoit, dites une fois par tournée.

        Elles ne sont ni notées ni résumées, mais leurs articles sont lus à la fin pour être
        marqués comme les autres : sans cela, une catégorie hors catalogue garderait ses
        compteurs de non-lus pour toujours, et le marquage dépendrait du catalogue.

        Calculées au moment de marquer, et seulement alors : un passage qui ne marquera
        pas (`--dry-run`, `--no-mark-read`, `--profil`) n'a aucune raison d'interroger
        FreshRSS pour elles.
        """
        catalogue = installation.catalogue
        if catalogue.ouvert:
            return []
        if installation.categories_surcharge is not None:
            disponibles = self._freshrss_client.list_categories()
        else:
            disponibles = installation.categories or self._freshrss_client.list_categories()
        categories = installation.categories_installation(
            disponibles
        )
        hors = catalogue.hors_catalogue(categories)
        usernames = self._annuaire.usernames()
        privees = [
            categorie
            for categorie in categories
            if categorie not in hors and not catalogue.servie_a(categorie, usernames)
        ]
        if hors:
            console.log(f"Catalogue : hors catalogue, servies à personne : {', '.join(hors)}")
        if privees:
            console.log(
                "Catalogue : privées sans propriétaire servi, servies à personne : "
                f"{', '.join(privees)}"
            )
        return hors + privees

    def _articles_orphelins(self, installation: AppConfig, day: dt.date) -> list[Article]:
        """Les articles du jour des catégories que personne n'a reçues, à marquer lus.

        Une panne de lecture ici est journalisée et ne coûte que ces articles-là : les
        emails sont déjà partis, et lever maintenant laisserait toute la journée non lue —
        un rejeu renverrait alors chaque email. Les orphelines resteront non lues, ce qui
        ne coûte qu'un compteur dans FreshRSS.
        """
        try:
            return [
                article
                for categorie in self._orphelines(installation)
                for article in self._freshrss_client.fetch_daily_articles(categorie, day)
            ]
        except Exception as exc:  # noqa: BLE001 — le marquage de ce qui a été servi d'abord
            console.error(
                f"Catalogue : lecture des catégories servies à personne impossible ({exc!r}) ; "
                "seul ce qui a été servi est marqué lu"
            )
            return []

    def _servir(
        self, installation: AppConfig, nom: str, day: dt.date, send_email: bool, write_tags: bool
    ) -> list[Article]:
        """Le digest d'une personne, sans marquage : rend ce qu'il a lu."""
        config = installation.pour(self._annuaire.lecteur(nom))
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
