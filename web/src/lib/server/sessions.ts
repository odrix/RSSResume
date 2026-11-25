/**
 * Les sessions : un jeton aléatoire dans un cookie, son empreinte SHA-256 en base.
 *
 * Seule l'empreinte est stockée : une copie de la base ne suffit pas à se faire passer
 * pour quelqu'un. SHA-256 et non Argon2 parce que le jeton a 256 bits d'entropie — rien à
 * deviner, donc rien à ralentir, et la vérification a lieu à chaque requête.
 */

import { createHash, randomBytes } from 'node:crypto';
import type { DatabaseSync } from 'node:sqlite';
import type { Comptes, Utilisateur } from './comptes.js';

export const COOKIE_SESSION = 'session';
const JOUR_MS = 24 * 60 * 60 * 1000;
export const DUREE_SESSION_MS = 30 * JOUR_MS;
/** En deçà, la session est prolongée : quelqu'un qui revient chaque semaine ne se
 * reconnecte jamais, une session abandonnée expire en un mois. */
const SEUIL_PROLONGATION_MS = 15 * JOUR_MS;

export interface SessionValide {
	utilisateur: Utilisateur;
	expireLe: Date;
	/** Vrai quand l'échéance a été repoussée : le cookie doit l'être aussi. */
	prolongee: boolean;
}

export class Sessions {
	constructor(
		private readonly base: DatabaseSync,
		private readonly comptes: Comptes,
		private readonly maintenant: () => number = Date.now
	) {}

	/** Rend le jeton à poser dans le cookie ; il n'est conservé nulle part ailleurs. */
	ouvrir(compteId: number): { jeton: string; expireLe: Date } {
		const jeton = randomBytes(32).toString('base64url');
		const expireLe = this.maintenant() + DUREE_SESSION_MS;
		this.base
			.prepare('INSERT INTO sessions (id, compte_id, expire_le) VALUES (?, ?, ?)')
			.run(empreinte(jeton), compteId, expireLe);
		return { jeton, expireLe: new Date(expireLe) };
	}

	valider(jeton: string): SessionValide | null {
		const id = empreinte(jeton);
		const ligne = this.base
			.prepare('SELECT compte_id, expire_le FROM sessions WHERE id = ?')
			.get(id) as { compte_id: number; expire_le: number } | undefined;
		if (!ligne) return null;
		const maintenant = this.maintenant();
		if (ligne.expire_le <= maintenant) {
			this.base.prepare('DELETE FROM sessions WHERE id = ?').run(id);
			return null;
		}
		const utilisateur = this.comptes.parId(ligne.compte_id);
		// La connexion refuse déjà un compte en attente ; la session le refuse aussi, pour
		// que la règle ne dépende pas d'un seul point d'entrée.
		if (!utilisateur?.confirme) return null;
		this.comptes.noterDerniereConnexion(ligne.compte_id);
		let expireLe = ligne.expire_le;
		const prolongee = expireLe - maintenant < SEUIL_PROLONGATION_MS;
		if (prolongee) {
			expireLe = maintenant + DUREE_SESSION_MS;
			this.base.prepare('UPDATE sessions SET expire_le = ? WHERE id = ?').run(expireLe, id);
		}
		return { utilisateur, expireLe: new Date(expireLe), prolongee };
	}

	fermer(jeton: string): void {
		this.base.prepare('DELETE FROM sessions WHERE id = ?').run(empreinte(jeton));
	}

	/** Après un changement de mot de passe : une session volée ne doit pas survivre à ce que
	 * la personne fait justement pour reprendre la main. `sauf` garde celle d'où elle agit. */
	fermerToutes(compteId: number, sauf?: string): void {
		if (sauf) {
			this.base
				.prepare('DELETE FROM sessions WHERE compte_id = ? AND id <> ?')
				.run(compteId, empreinte(sauf));
		} else {
			this.base.prepare('DELETE FROM sessions WHERE compte_id = ?').run(compteId);
		}
	}

	purgerExpirees(): void {
		this.base.prepare('DELETE FROM sessions WHERE expire_le <= ?').run(this.maintenant());
	}
}

function empreinte(jeton: string): string {
	return createHash('sha256').update(jeton).digest('hex');
}
