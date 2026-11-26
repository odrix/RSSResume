/**
 * Les journées qu'une personne a déjà lues ou écoutées, pour les distinguer dans sa liste.
 *
 * Un marquage n'appartient qu'à celui qui lit : le compte écrit vient toujours de la session,
 * jamais de l'URL. Le username de l'URL ne sert qu'à refuser — un administrateur qui ouvre la
 * journée d'un autre ne la marque pas, ni pour lui (ce n'est pas sa journée) ni pour l'autre.
 *
 * Sans rapport avec le marquage comme lu des articles dans FreshRSS, qui reste du ressort du
 * passage quotidien.
 */

import type { DatabaseSync } from 'node:sqlite';
import type { Utilisateur } from './comptes.js';
import { MOTIF_DATE } from './consultation.js';
import { MOTIF_USERNAME } from './validation.js';

/** Ce qui a marqué la journée : l'ouverture de ses pages, ou la fin de son audio. */
export type OrigineLecture = 'pages' | 'audio';

export class JourneesLues {
	constructor(
		private readonly base: DatabaseSync,
		private readonly maintenant: () => number = Date.now
	) {}

	/** `false` sans rien écrire si la journée n'est pas celle de la personne connectée.
	 *
	 * `INSERT OR IGNORE` : lire puis écouter la même journée ne fait qu'une ligne, et la
	 * première manière de l'avoir lue est celle qui reste. */
	marquer(utilisateur: Utilisateur, username: string, date: string, origine: OrigineLecture): boolean {
		if (!this.peutMarquer(utilisateur, username, date)) return false;
		this.base
			.prepare('INSERT OR IGNORE INTO journees_lues (compte_id, date, origine, lue_le) VALUES (?, ?, ?, ?)')
			.run(utilisateur.id, date, origine, new Date(this.maintenant()).toISOString());
		return true;
	}

	/** Vide pour qui regarde la liste d'un autre : ses propres lectures n'y auraient pas de sens,
	 * et celles de l'autre ne le regardent pas. */
	lues(utilisateur: Utilisateur, username: string): Set<string> {
		if (!this.estSienne(utilisateur, username)) return new Set();
		const lignes = this.base
			.prepare('SELECT date FROM journees_lues WHERE compte_id = ?')
			.all(utilisateur.id) as { date: string }[];
		return new Set(lignes.map((ligne) => ligne.date));
	}

	/** Le contrôle de `marquer`, sans écrire : la route d'écoute le passe avant d'interroger
	 * l'API, pour ne marquer sans elle, quand elle est en panne, que ce qui est déjà vérifié. */
	peutMarquer(utilisateur: Utilisateur, username: string, date: string): boolean {
		return this.estSienne(utilisateur, username) && MOTIF_DATE.test(date);
	}

	private estSienne(utilisateur: Utilisateur, username: string): boolean {
		return username === utilisateur.username && MOTIF_USERNAME.test(username);
	}
}
