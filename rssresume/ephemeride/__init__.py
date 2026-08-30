"""L'éphéméride qui ouvre la lettre : un jour, sa fête, et un fait de cette date.

Tout ici porte sur le jour de l'ENVOI, jamais sur celui que le digest raconte. Le
passage de 7 h résume la veille (`RSSRESUME_SCHEDULE_DAYS_BACK`) : une lettre ouverte
sur la date du digest arriverait datée d'un jour dans la boîte de son lecteur.

    from rssresume import ephemeride

    ephemeride.EphemerideService(provider).of(jour)   # à l'envoi
    ephemeride.pour_envoi(relue, jour)                # au renvoi, sans aucun appel

Le paquet sépare les données du procédé, parce que les unes se corrigent bien plus
souvent que l'autre :

- `fetes` : la fête de chaque date, 366 entrées, le calendrier des postes ;
- `histoire` : les dates marquantes du domaine, table de repli du modèle ;
- `service` : l'assemblage, les marches de repli, et ce qu'un renvoi doit rouvrir.

Ce module ne réexporte que la façade. Corriger un saint se fait dans `fetes`, ajouter
une date dans `histoire`, et ni l'un ni l'autre n'oblige à relire le procédé.
"""

from rssresume.ephemeride import fetes, histoire
from rssresume.ephemeride.service import (
    AUCUNE,
    LONGUEUR_MAX,
    EphemerideService,
    calendrier,
    pour_envoi,
    table,
)

__all__ = [
    "AUCUNE",
    "LONGUEUR_MAX",
    "EphemerideService",
    "calendrier",
    "fetes",
    "histoire",
    "pour_envoi",
    "table",
]
