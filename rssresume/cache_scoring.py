"""Le cache de scoring en base SQLite : une note par article et par empreinte de prompt.

Le cache vivait dans des libellés FreshRSS préfixés par profil (`score-NN`, `theme-*`,
`scoring-<hash>`). Il vit ici, dans la même base que l'annuaire des profils, clé
(item_id, empreinte) : deux profils au texte identique ont la même empreinte de scoring,
donc la même note, sans mutualisation par gabarit. L'angle, enfin persisté, y est.

Même ouverture qu'`AnnuaireSqlite` : une connexion par opération, WAL et
`busy_timeout`, schéma garanti à chaque ouverture. Le travailleur écrit, personne
ne lit en même temps depuis l'API, mais le mode WAL ne coûte rien et garde la porte
ouverte à une lecture depuis le site.

`digested` et le marquage comme lu restent dans FreshRSS : ce ne sont pas des notes.
"""

from __future__ import annotations

import contextlib
import pathlib
import sqlite3
from typing import Iterator

from rssresume.annuaire_sqlite import ATTENTE_VERROU_MS
from rssresume.models import Note

_SCHEMA_SCORES = """
CREATE TABLE IF NOT EXISTS scores (
    item_id    TEXT NOT NULL,
    empreinte  TEXT NOT NULL,
    score      INTEGER NOT NULL,
    thematique TEXT NOT NULL,
    angle      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (item_id, empreinte)
)
"""


class CacheScoringSqlite:
    """Les notes du scoring dans la base SQLite des profils, une ligne par (article, empreinte).

    Une connexion par opération, fermée aussitôt : comme l'annuaire, une connexion ne
    se partage pas entre fils, et l'ouverture coûte moins qu'une requête. Une empreinte
    obsolète ne nettoie rien : sa ligne reste, simplement inatteignable, et la note
    courante s'écrit à côté sous la nouvelle empreinte.
    """

    def __init__(self, chemin: pathlib.Path):
        self.chemin = pathlib.Path(chemin)
        with self._connexion():
            pass

    @contextlib.contextmanager
    def _connexion(self) -> Iterator[sqlite3.Connection]:
        """Une connexion en autocommit, WAL posé, schéma garanti."""
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        connexion = sqlite3.connect(
            self.chemin, timeout=ATTENTE_VERROU_MS / 1000, isolation_level=None
        )
        try:
            connexion.execute(f"PRAGMA busy_timeout = {ATTENTE_VERROU_MS}")
            connexion.execute("PRAGMA journal_mode = WAL")
            connexion.execute(_SCHEMA_SCORES)
            yield connexion
        finally:
            connexion.close()

    def note(self, item_id: str, empreinte: str) -> Note | None:
        """La note de l'article sous cette empreinte, angle compris, ou `None`."""
        with self._connexion() as connexion:
            ligne = connexion.execute(
                "SELECT score, thematique, angle FROM scores WHERE item_id = ? AND empreinte = ?",
                (item_id, empreinte),
            ).fetchone()
        if ligne is None:
            return None
        score, thematique, angle = ligne
        return Note(score=int(score), thematique=thematique, angle=angle)

    def enregistrer(self, item_id: str, empreinte: str, note: Note) -> None:
        """Écrit la note, en remplaçant une note antérieure sous la même clé.

        `ON CONFLICT` et non une lecture suivie d'une écriture : la clé primaire est ce
        qui fait qu'une seconde écriture sous la même empreinte écrase la première.
        """
        with self._connexion() as connexion:
            connexion.execute(
                "INSERT INTO scores (item_id, empreinte, score, thematique, angle) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (item_id, empreinte) DO UPDATE SET "
                "score = excluded.score, thematique = excluded.thematique, angle = excluded.angle",
                (item_id, empreinte, int(note.score), note.thematique, note.angle),
            )
