/**
 * La base des comptes du site : `node:sqlite`, intégré à Node, plutôt qu'un pilote natif.
 *
 * Même parti que l'appli Python, qui tient sur la bibliothèque standard : pas de module
 * compilé à reconstruire à chaque version de Node ni dans l'image alpine, et une API
 * synchrone qui suffit à quelques comptes. Les profils ne sont pas ici — ils appartiennent
 * à l'appli de résumé ; le site ne garde que de quoi authentifier.
 */

import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

/** Une entrée par version du schéma, appliquées dans l'ordre ; `user_version` dit où on en est. */
const MIGRATIONS = [
	`CREATE TABLE comptes (
		id INTEGER PRIMARY KEY,
		email TEXT NOT NULL UNIQUE COLLATE NOCASE,
		username TEXT NOT NULL UNIQUE,
		hash TEXT NOT NULL,
		role TEXT NOT NULL DEFAULT 'membre' CHECK (role IN ('membre', 'admin')),
		cree_le TEXT NOT NULL
	);
	CREATE TABLE sessions (
		id TEXT PRIMARY KEY,
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		expire_le INTEGER NOT NULL
	);
	CREATE INDEX sessions_compte ON sessions (compte_id);`
];

/** `:memory:` pour les tests ; un chemin de fichier sinon, dont le dossier est créé. */
export function ouvrirBase(chemin: string): DatabaseSync {
	if (chemin !== ':memory:') mkdirSync(dirname(chemin), { recursive: true });
	const base = new DatabaseSync(chemin);
	base.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');
	migrer(base);
	return base;
}

function migrer(base: DatabaseSync): void {
	const { user_version: version } = base.prepare('PRAGMA user_version').get() as {
		user_version: number;
	};
	for (let i = version; i < MIGRATIONS.length; i++) {
		base.exec('BEGIN');
		try {
			base.exec(MIGRATIONS[i]);
			base.exec(`PRAGMA user_version = ${i + 1}`);
			base.exec('COMMIT');
		} catch (erreur) {
			base.exec('ROLLBACK');
			throw erreur;
		}
	}
}
