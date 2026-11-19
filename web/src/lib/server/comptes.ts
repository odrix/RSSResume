/**
 * Les comptes du site : qui peut se connecter, et ce qu'il a le droit de voir.
 */

import { hash, verify } from '@node-rs/argon2';
import type { DatabaseSync } from 'node:sqlite';
import { normaliserEmail } from './validation.js';

export type Role = 'membre' | 'admin';

/** Argon2id aux réglages par défaut de @node-rs/argon2 (19 Mio, 2 passes), le minimum que
 * recommande l'OWASP. Une classe à part pour que les tests la remplacent par plus rapide. */
export class HacheurMotDePasse {
	hacher(motDePasse: string): Promise<string> {
		return hash(motDePasse);
	}

	async verifier(empreinte: string, motDePasse: string): Promise<boolean> {
		try {
			return await verify(empreinte, motDePasse);
		} catch {
			return false;
		}
	}
}

/** La personne connectée. Le droit d'administrer est calculé une fois, au chargement. */
export class Utilisateur {
	constructor(
		readonly id: number,
		readonly email: string,
		readonly username: string,
		readonly role: Role,
		readonly admin: boolean
	) {}

	/** Un résumé se consulte par son propriétaire, ou par l'administrateur. */
	peutConsulter(username: string): boolean {
		return this.admin || this.username === username;
	}

	/** Ce que la page a le droit de savoir : ni l'id ni le rôle brut n'y servent. */
	pourPage(): { email: string; username: string; admin: boolean } {
		return { email: this.email, username: this.username, admin: this.admin };
	}
}

export interface LigneCompte {
	id: number;
	email: string;
	username: string;
	role: Role;
	cree_le: string;
}

export class CompteExistant extends Error {
	constructor(readonly champ: 'email' | 'username') {
		super(champ === 'email' ? 'Cette adresse a déjà un compte.' : "Ce nom d'utilisateur est pris.");
	}
}

export class Comptes {
	/** Une empreinte jetable, vérifiée quand l'adresse est inconnue : la réponse prend alors
	 * le même temps qu'un mauvais mot de passe, et ne dit pas quelles adresses existent. */
	#empreinteLeurre: Promise<string> | null = null;

	constructor(
		private readonly base: DatabaseSync,
		/** L'adresse de `ADMIN_EMAIL` ; vide, seul le rôle en base fait un administrateur. */
		private readonly emailAdmin: string,
		private readonly hacheur: HacheurMotDePasse = new HacheurMotDePasse()
	) {}

	/** Ce qui empêcherait la création, vérifié avant d'appeler l'API : un profil créé pour
	 * un compte qui ne peut pas l'être serait un orphelin à supprimer. */
	conflit(email: string, username: string): CompteExistant | null {
		const ligne = this.base
			.prepare('SELECT email, username FROM comptes WHERE email = ? OR username = ?')
			.get(normaliserEmail(email), username) as { email: string; username: string } | undefined;
		if (!ligne) return null;
		return new CompteExistant(ligne.username === username ? 'username' : 'email');
	}

	async creer(email: string, username: string, motDePasse: string): Promise<Utilisateur> {
		const empreinte = await this.hacheur.hacher(motDePasse);
		try {
			const resultat = this.base
				.prepare('INSERT INTO comptes (email, username, hash, cree_le) VALUES (?, ?, ?, ?)')
				.run(normaliserEmail(email), username, empreinte, new Date().toISOString());
			return this.parId(Number(resultat.lastInsertRowid))!;
		} catch (erreur) {
			// Une course entre deux inscriptions : la contrainte UNIQUE tranche.
			const conflit = this.conflit(email, username);
			if (conflit) throw conflit;
			throw erreur;
		}
	}

	async authentifier(email: string, motDePasse: string): Promise<Utilisateur | null> {
		const ligne = this.base
			.prepare('SELECT id, hash FROM comptes WHERE email = ?')
			.get(normaliserEmail(email)) as { id: number; hash: string } | undefined;
		if (!ligne) {
			this.#empreinteLeurre ??= this.hacheur.hacher('leurre-pour-un-temps-constant');
			await this.hacheur.verifier(await this.#empreinteLeurre, motDePasse);
			return null;
		}
		if (!(await this.hacheur.verifier(ligne.hash, motDePasse))) return null;
		return this.parId(ligne.id);
	}

	parId(id: number): Utilisateur | null {
		const ligne = this.base
			.prepare('SELECT id, email, username, role FROM comptes WHERE id = ?')
			.get(id) as LigneCompte | undefined;
		return ligne ? this.#utilisateur(ligne) : null;
	}

	supprimer(id: number): void {
		this.base.prepare('DELETE FROM comptes WHERE id = ?').run(id);
	}

	lister(): (LigneCompte & { admin: boolean })[] {
		const lignes = this.base
			.prepare('SELECT id, email, username, role, cree_le FROM comptes ORDER BY username')
			.all() as unknown as LigneCompte[];
		return lignes.map((ligne) => ({ ...ligne, admin: this.#estAdmin(ligne) }));
	}

	#estAdmin(ligne: Pick<LigneCompte, 'role' | 'email'>): boolean {
		return (
			ligne.role === 'admin' ||
			(this.emailAdmin !== '' && normaliserEmail(this.emailAdmin) === ligne.email)
		);
	}

	#utilisateur(ligne: LigneCompte): Utilisateur {
		return new Utilisateur(ligne.id, ligne.email, ligne.username, ligne.role, this.#estAdmin(ligne));
	}
}
