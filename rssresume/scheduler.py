"""Exécution quotidienne : attendre l'heure dite, lancer le digest, recommencer.

Le conteneur ne fait rien d'autre. Un `cron` aurait pu suffire, mais il n'hérite pas de
l'environnement du conteneur — c'est justement là que Dokploy pose les clés d'API et les
identifiants FreshRSS — et il ne connaît pas `RSSRESUME_TIMEZONE`. Une boucle en Python
lit le même environnement que le reste, découpe les journées dans le même fuseau, et
n'ajoute pas un octet à l'image.

Deux réglages, et rien de plus :

- `RSSRESUME_SCHEDULE` : l'heure du passage, dans `RSSRESUME_TIMEZONE` (défaut 07:00) ;
- `RSSRESUME_SCHEDULE_DAYS_BACK` : la journée digérée, comptée depuis celle du passage
  (défaut 1, la veille).

Le second n'est pas un détail : un passage à 7 h qui digérerait « aujourd'hui » ne
lirait que les articles parus entre minuit et 7 h. Le digest du matin raconte la veille.
"""

from __future__ import annotations

import datetime as dt
import os
import signal
import threading

from rssresume import cli
from rssresume.config import AppConfig
from rssresume.tools import console

#: Heure du passage quotidien, `HH:MM` dans le fuseau configuré.
ENV_SCHEDULE = "RSSRESUME_SCHEDULE"
DEFAULT_SCHEDULE = "07:00"

#: Journée digérée, en nombre de jours avant celui du passage. `0` = le jour même.
ENV_DAYS_BACK = "RSSRESUME_SCHEDULE_DAYS_BACK"
DEFAULT_DAYS_BACK = 1


def parse_schedule(value: str | None) -> dt.time:
    """`HH:MM` → l'heure du passage. Une valeur illisible échoue au lancement.

    Le conteneur ne redémarre qu'au déploiement : une heure mal écrite qu'on ignorerait
    en silence ne se verrait qu'au premier matin sans digest.
    """
    texte = (value or DEFAULT_SCHEDULE).strip() or DEFAULT_SCHEDULE
    try:
        heure = dt.time.fromisoformat(texte)
    except ValueError as exc:
        raise ValueError(f"{ENV_SCHEDULE} : « {texte} » n'est pas une heure « HH:MM » ({exc})") from exc
    if heure.tzinfo is not None:
        raise ValueError(f"{ENV_SCHEDULE} : « {texte} » porte un fuseau, que {ENV_SCHEDULE} ne lit pas")
    return heure


def parse_days_back(value: str | None) -> int:
    texte = (value or "").strip()
    if not texte:
        return DEFAULT_DAYS_BACK
    if not texte.isdigit():
        raise ValueError(f"{ENV_DAYS_BACK} : « {texte} » n'est pas un nombre de jours positif")
    return int(texte)


class DailySchedule:
    """L'heure dite dans un fuseau : le prochain passage, et la journée qu'il digère."""

    def __init__(self, heure: dt.time, timezone: dt.tzinfo, days_back: int = DEFAULT_DAYS_BACK):
        self.heure = heure
        self.timezone = timezone
        self.days_back = days_back

    @classmethod
    def from_env(cls, timezone: dt.tzinfo) -> "DailySchedule":
        return cls(
            heure=parse_schedule(os.getenv(ENV_SCHEDULE)),
            timezone=timezone,
            days_back=parse_days_back(os.getenv(ENV_DAYS_BACK)),
        )

    def next_run(self, moment: dt.datetime) -> dt.datetime:
        """Le prochain passage strictement après `moment`, en heure locale."""
        local = moment.astimezone(self.timezone)
        passage = dt.datetime.combine(local.date(), self.heure, tzinfo=self.timezone)
        if passage <= local:
            passage += dt.timedelta(days=1)
        return passage

    def target_day(self, passage: dt.datetime) -> dt.date:
        """La journée que ce passage doit raconter : la veille, sauf réglage contraire."""
        return passage.astimezone(self.timezone).date() - dt.timedelta(days=self.days_back)


def stop_on_signal() -> threading.Event:
    """Un drapeau levé par SIGTERM et SIGINT, pour sortir de l'attente sans attendre.

    En PID 1 — ce qu'est le processus dans le conteneur — le noyau n'applique aucune
    action par défaut aux signaux : sans ce gestionnaire, un `docker stop` serait ignoré
    dix secondes puis suivi d'un SIGKILL.
    """
    arret = threading.Event()
    for numero in (signal.SIGTERM, signal.SIGINT):
        signal.signal(numero, lambda *_: arret.set())
    return arret


def run_forever(
    schedule: DailySchedule,
    run=cli.main,
    attendre=None,
    maintenant=None,
    passages: int | None = None,
) -> int:
    """Boucle : dormir jusqu'au prochain passage, lancer le digest de sa journée.

    `attendre(secondes)` rend vrai quand il faut s'arrêter — c'est l'attente elle-même
    qui écoute le signal. `passages` borne la boucle, pour les tests.

    Un digest qui échoue est journalisé et la boucle continue : FreshRSS injoignable ou
    un fournisseur en panne un matin ne doit pas coûter tous les matins suivants.
    """
    attendre = attendre or stop_on_signal().wait
    maintenant = maintenant or (lambda: dt.datetime.now(schedule.timezone))

    console.log(
        f"RSSResume : passage quotidien à {schedule.heure.isoformat('minutes')} "
        f"({schedule.timezone}), journée digérée : J-{schedule.days_back}"
    )
    # Le curseur, et non l'horloge, décide du passage suivant : un réveil quelques
    # millisecondes trop tôt relancerait sinon le passage qui vient d'avoir lieu.
    curseur = maintenant()
    restants = passages
    while restants is None or restants > 0:
        passage = schedule.next_run(curseur)
        console.log(f"Prochain passage : {passage.isoformat(timespec='seconds')}")
        if attendre(max(0.0, (passage - maintenant()).total_seconds())):
            console.log("Arrêt demandé.")
            return 0
        jour = schedule.target_day(passage)
        try:
            run(["--date", jour.isoformat()])
        except Exception as exc:  # noqa: BLE001 — un matin perdu, pas tous les suivants
            console.log(f"Échec du digest du {jour.isoformat()} : {exc!r}")
        curseur = passage
        if restants is not None:
            restants -= 1
    return 0


def main() -> int:
    """La configuration est lue ici, au lancement, pour échouer tout de suite.

    Une clé manquante ou un fuseau inconnu doit faire crasher le conteneur au
    déploiement — visible dans Dokploy — plutôt qu'au premier matin.
    """
    config = AppConfig.from_env()
    return run_forever(DailySchedule.from_env(config.timezone))


if __name__ == "__main__":
    raise SystemExit(main())
