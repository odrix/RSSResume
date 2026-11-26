/**
 * La base des comptes du site : `node:sqlite`, intégré à Node, plutôt qu'un pilote natif.
 *
 * Même parti que l'appli Python, qui tient sur la bibliothèque standard : pas de module
 * compilé à reconstruire à chaque version de Node ni dans l'image alpine, et une API
 * synchrone qui suffit à quelques comptes. Les profils ne sont pas ici, ils appartiennent
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
	CREATE INDEX sessions_compte ON sessions (compte_id);`,
	// La vérification d'email. Un compte naît en attente (`confirme_le` nul) et garde le
	// texte saisi à l'inscription jusqu'à la confirmation, qui seule crée le profil côté API.
	// Les comptes antérieurs sont tenus pour confirmés : ils ont été créés avant la règle.
	`ALTER TABLE comptes ADD COLUMN confirme_le TEXT;
	ALTER TABLE comptes ADD COLUMN brouillon_profil TEXT;
	ALTER TABLE comptes ADD COLUMN brouillon_prenom TEXT;
	UPDATE comptes SET confirme_le = cree_le;
	CREATE TABLE jetons_email (
		id TEXT PRIMARY KEY,
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		email TEXT NOT NULL,
		objet TEXT NOT NULL CHECK (objet IN ('inscription', 'destinataire')),
		expire_le INTEGER NOT NULL
	);
	CREATE INDEX jetons_email_compte ON jetons_email (compte_id);
	CREATE TABLE destinataires_en_attente (
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		email TEXT NOT NULL COLLATE NOCASE,
		PRIMARY KEY (compte_id, email)
	);`,
	// Le métier choisi à l'inscription : une copie des réglages du gabarit, gardée avec le
	// brouillon pour que le profil créé à la confirmation soit celui que la personne a vu,
	// même si le catalogue change entre-temps. Et la première connexion, qui mène au profil
	// plutôt qu'à une liste de résumés encore vide. Un compte déjà confirmé a reçu son
	// profil et ses résumés sous l'ancienne règle : le renvoyer au profil le dérouterait.
	`ALTER TABLE comptes ADD COLUMN brouillon_gabarit TEXT;
	ALTER TABLE comptes ADD COLUMN premiere_connexion_le TEXT;
	UPDATE comptes SET premiere_connexion_le = confirme_le WHERE confirme_le IS NOT NULL;`,
	// L’usage du site : dernière connexion et consultations, une fois par profil et par jour.
	`ALTER TABLE comptes ADD COLUMN derniere_connexion_le TEXT;
	CREATE TABLE consultations (
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		jour TEXT NOT NULL,
		PRIMARY KEY (compte_id, jour)
	);
	CREATE INDEX consultations_jour ON consultations (jour);`,
	// Deux nouveaux objets de lien : le mot de passe oublié et le changement d'adresse du
	// compte. SQLite ne sait pas modifier une contrainte CHECK : la table est recopiée.
	`CREATE TABLE jetons_email_v5 (
		id TEXT PRIMARY KEY,
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		email TEXT NOT NULL,
		objet TEXT NOT NULL CHECK (objet IN ('inscription', 'destinataire', 'reinitialisation', 'adresse')),
		expire_le INTEGER NOT NULL
	);
	INSERT INTO jetons_email_v5 SELECT id, compte_id, email, objet, expire_le FROM jetons_email;
	DROP TABLE jetons_email;
	ALTER TABLE jetons_email_v5 RENAME TO jetons_email;
	CREATE INDEX jetons_email_compte ON jetons_email (compte_id);`,
	// Magic-link : compte sans mot de passe possible, et suivi des demandes par IP/email.
	// Hash devient nullable : un compte peut utiliser un magic-link au lieu d'un mot de passe.
	`ALTER TABLE comptes ADD COLUMN hash_temp TEXT;
	UPDATE comptes SET hash_temp = hash;
	ALTER TABLE comptes DROP COLUMN hash;
	ALTER TABLE comptes ADD COLUMN hash TEXT;
	UPDATE comptes SET hash = hash_temp;
	ALTER TABLE comptes DROP COLUMN hash_temp;
	CREATE TABLE magic_link_demandes (
		email TEXT NOT NULL COLLATE NOCASE,
		ip TEXT NOT NULL,
		demande_le INTEGER NOT NULL,
		PRIMARY KEY (email, ip, demande_le)
	);
	CREATE INDEX magic_link_demandes_email ON magic_link_demandes (email, demande_le);
	CREATE INDEX magic_link_demandes_ip ON magic_link_demandes (ip, demande_le);`,
	// Ajout de l'objet 'magic-link' à la contrainte CHECK de jetons_email.
	// SQLite ne permet pas de modifier une contrainte CHECK existante sans recréer la table.
	`CREATE TABLE jetons_email_v6 (
		id TEXT PRIMARY KEY,
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		email TEXT NOT NULL,
		objet TEXT NOT NULL CHECK (objet IN ('inscription', 'destinataire', 'reinitialisation', 'adresse', 'magic-link')),
		expire_le INTEGER NOT NULL
	);
	INSERT INTO jetons_email_v6 SELECT id, compte_id, email, objet, expire_le FROM jetons_email;
	DROP TABLE jetons_email;
	ALTER TABLE jetons_email_v6 RENAME TO jetons_email;
	CREATE INDEX jetons_email_compte ON jetons_email (compte_id);`,
	// Une demande de magic-link est un événement, pas une entité : deux demandes dans la même
	// milliseconde (un double clic) faisaient échouer la seconde sur la clé primaire.
	`CREATE TABLE magic_link_demandes_v8 (
		email TEXT NOT NULL COLLATE NOCASE,
		ip TEXT NOT NULL,
		demande_le INTEGER NOT NULL
	);
	INSERT INTO magic_link_demandes_v8 SELECT email, ip, demande_le FROM magic_link_demandes;
	DROP TABLE magic_link_demandes;
	ALTER TABLE magic_link_demandes_v8 RENAME TO magic_link_demandes;
	CREATE INDEX magic_link_demandes_email ON magic_link_demandes (email, demande_le);
	CREATE INDEX magic_link_demandes_ip ON magic_link_demandes (ip, demande_le);`,
	// Les journées lues ou écoutées. Distinct de `consultations`, dont la clé est le jour de la
	// visite et non la journée lue. Une ligne par compte et par journée : lire puis écouter ne
	// compte qu'une fois, et la première origine est celle qui reste.
	`CREATE TABLE journees_lues (
		compte_id INTEGER NOT NULL REFERENCES comptes (id) ON DELETE CASCADE,
		date TEXT NOT NULL,
		origine TEXT NOT NULL CHECK (origine IN ('pages', 'audio')),
		lue_le TEXT NOT NULL,
		PRIMARY KEY (compte_id, date)
	);`
];

/** `:memory:` pour les tests ; un chemin de fichier sinon, dont le dossier est créé. */
export function ouvrirBase(chemin: string): DatabaseSync {
	if (chemin !== ':memory:') mkdirSync(dirname(chemin), { recursive: true });
	const base = new DatabaseSync(chemin);
	base.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');
	migrer(base);
	return base;
}

/** `cible` ne sert qu'aux tests : arrêter une base à une version ancienne, y mettre des
 * comptes, puis vérifier ce que la migration suivante en fait. */
export function migrer(base: DatabaseSync, cible = MIGRATIONS.length): void {
	const { user_version: version } = base.prepare('PRAGMA user_version').get() as {
		user_version: number;
	};
	for (let i = version; i < cible; i++) {
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
