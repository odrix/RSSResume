/**
 * Les comptes du site : qui peut se connecter, et ce qu'il a le droit de voir.
 *
 * Un compte naît en attente : tant que son adresse n'est pas confirmée, il ne se connecte
 * pas, n'a pas de profil côté API et n'est administrateur de rien. L'inscription est
 * ouverte ; c'est la confirmation qui prouve qu'on parle au titulaire de l'adresse.
 */

import { hash, verify } from '@node-rs/argon2';
import type { DatabaseSync } from 'node:sqlite';
import type { Axe, ComposantStack, Securite } from '#lib/profil.js';
import { normaliserEmail } from './validation.js';

export type Role = 'membre' | 'admin';

/** Un compte jamais confirmé disparaît au bout de ce délai : il libère son adresse et son
 * username, qu'une faute de frappe ou un usurpateur aurait sinon pris pour toujours. */
export const DELAI_CONFIRMATION_COMPTE_MS = 7 * 24 * 60 * 60 * 1000;

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

/** Une personne qui a un compte. Le droit d'administrer est calculé une fois, au chargement. */
export class Utilisateur {
	constructor(
		readonly id: number,
		readonly email: string,
		readonly username: string,
		readonly role: Role,
		readonly admin: boolean,
		readonly confirme: boolean
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

/** Les réglages du gabarit choisi à l'inscription, copiés plutôt que désignés par leur
 * `metier` : le profil créé à la confirmation reprend ce que la personne a vu, même si
 * le catalogue des gabarits a changé entre-temps. Le texte, lui, est dans `profil`. */
export interface ReglagesGabarit {
	metier: string;
	libelle: string;
	stack: ComposantStack[];
	securite: Securite;
	axes: Axe[];
	categories: string[];
}

/** Ce que la personne a écrit à l'inscription, gardé jusqu'à la création du profil.
 * `gabarit` est nul pour « Autre » : le profil n'aura alors ni axes ni catégories. */
export interface Brouillon {
	profil: string;
	prenom: string;
	gabarit: ReglagesGabarit | null;
}

interface LigneCompte {
	id: number;
	email: string;
	username: string;
	role: Role;
	cree_le: string;
	confirme_le: string | null;
	derniere_connexion_le: string | null;
}

export interface CompteListe {
	id: number;
	email: string;
	username: string;
	creeLe: string;
	derniereConnexionLe: string | null;
	confirme: boolean;
	admin: boolean;
}

export class CompteExistant extends Error {
	constructor(readonly champ: 'email' | 'username') {
		super(champ === 'email' ? 'Cette adresse a déjà un compte.' : "Ce nom d'utilisateur est pris.");
	}
}

const COLONNES = 'id, email, username, role, cree_le, confirme_le, derniere_connexion_le';

export class Comptes {
	/** Une empreinte jetable, vérifiée quand l'adresse est inconnue : la réponse prend alors
	 * le même temps qu'un mauvais mot de passe, et ne dit pas quelles adresses existent. */
	#empreinteLeurre: Promise<string> | null = null;

	constructor(
		private readonly base: DatabaseSync,
		/** L'adresse de `ADMIN_EMAIL` ; vide, seul le rôle en base fait un administrateur. */
		private readonly emailAdmin: string,
		private readonly hacheur: HacheurMotDePasse = new HacheurMotDePasse(),
		private readonly maintenant: () => number = Date.now
	) {}

	/** Ce qui empêcherait la création. Les comptes en attente comptent : leur adresse et
	 * leur username sont réservés jusqu'à la confirmation ou à la purge. */
	conflit(email: string, username: string): CompteExistant | null {
		const ligne = this.base
			.prepare('SELECT email, username FROM comptes WHERE email = ? OR username = ?')
			.get(normaliserEmail(email), username) as { email: string; username: string } | undefined;
		if (!ligne) return null;
		return new CompteExistant(ligne.username === username ? 'username' : 'email');
	}

	/** Crée un compte en attente de confirmation. */
	async creer(
		email: string,
		username: string,
		motDePasse: string,
		brouillon: Brouillon = { profil: '', prenom: '', gabarit: null }
	): Promise<Utilisateur> {
		const empreinte = await this.hacheur.hacher(motDePasse);
		try {
			const resultat = this.base
				.prepare(
					`INSERT INTO comptes (email, username, hash, cree_le, brouillon_profil, brouillon_prenom, brouillon_gabarit)
					VALUES (?, ?, ?, ?, ?, ?, ?)`
				)
				.run(
					normaliserEmail(email),
					username,
					empreinte,
					new Date(this.maintenant()).toISOString(),
					brouillon.profil,
					brouillon.prenom,
					brouillon.gabarit ? JSON.stringify(brouillon.gabarit) : null
				);
			return this.parId(Number(resultat.lastInsertRowid))!;
		} catch (erreur) {
			// Une course entre deux inscriptions : la contrainte UNIQUE tranche.
			const conflit = this.conflit(email, username);
			if (conflit) throw conflit;
			throw erreur;
		}
	}

	brouillon(id: number): Brouillon {
		const ligne = this.base
			.prepare('SELECT brouillon_profil, brouillon_prenom, brouillon_gabarit FROM comptes WHERE id = ?')
			.get(id) as
			| { brouillon_profil: string | null; brouillon_prenom: string | null; brouillon_gabarit: string | null }
			| undefined;
		return {
			profil: ligne?.brouillon_profil ?? '',
			prenom: ligne?.brouillon_prenom ?? '',
			gabarit: ligne?.brouillon_gabarit ? (JSON.parse(ligne.brouillon_gabarit) as ReglagesGabarit) : null
		};
	}

	/** Le brouillon a servi à créer le profil : il n'a plus de raison d'être gardé.
	 *
	 * Rend vrai pour le seul appel qui a fait passer le compte de l'attente à la
	 * confirmation : c'est à lui, et à lui seul, d'envoyer ce qui ne doit partir qu'une fois. */
	confirmer(id: number): boolean {
		const resultat = this.base
			.prepare(
				`UPDATE comptes
				SET confirme_le = ?, brouillon_profil = NULL, brouillon_prenom = NULL, brouillon_gabarit = NULL
				WHERE id = ? AND confirme_le IS NULL`
			)
			.run(new Date(this.maintenant()).toISOString(), id);
		return Number(resultat.changes) === 1;
	}

	/** Note la première connexion, et rend vrai si c'est elle : la première mène au profil,
	 * pour que la personne relise ce qui décidera de ses articles avant le premier envoi. */
	noterPremiereConnexion(id: number): boolean {
		const resultat = this.base
			.prepare('UPDATE comptes SET premiere_connexion_le = ? WHERE id = ? AND premiere_connexion_le IS NULL')
			.run(new Date(this.maintenant()).toISOString(), id);
		return Number(resultat.changes) === 1;
	}

	/** Note le moment d’une session valide : distinct de la première connexion,
	 * qui garde sa valeur initiale pour mener la personne une seule fois au profil. */
	noterDerniereConnexion(id: number): void {
		this.base
			.prepare('UPDATE comptes SET derniere_connexion_le = ? WHERE id = ? AND confirme_le IS NOT NULL')
			.run(new Date(this.maintenant()).toISOString(), id);
	}

	/** Vérifie le mot de passe, confirmé ou non : c'est à l'appelant de refuser un compte en
	 * attente, avec un message que seul le titulaire du mot de passe verra. */
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

	async changerMotDePasse(id: number, motDePasse: string): Promise<void> {
		const empreinte = await this.hacheur.hacher(motDePasse);
		this.base.prepare('UPDATE comptes SET hash = ? WHERE id = ?').run(empreinte, id);
	}

	/** L'adresse ne change qu'une fois la nouvelle prouvée : c'est à l'appelant d'avoir
	 * consommé le lien. La contrainte UNIQUE tranche une course avec une inscription. */
	changerEmail(id: number, email: string): void {
		try {
			this.base.prepare('UPDATE comptes SET email = ? WHERE id = ?').run(normaliserEmail(email), id);
		} catch (erreur) {
			if (this.parEmail(email)) throw new CompteExistant('email');
			throw erreur;
		}
	}

	parId(id: number): Utilisateur | null {
		const ligne = this.base.prepare(`SELECT ${COLONNES} FROM comptes WHERE id = ?`).get(id) as
			| LigneCompte
			| undefined;
		return ligne ? this.#utilisateur(ligne) : null;
	}

	parEmail(email: string): Utilisateur | null {
		const ligne = this.base
			.prepare(`SELECT ${COLONNES} FROM comptes WHERE email = ?`)
			.get(normaliserEmail(email)) as LigneCompte | undefined;
		return ligne ? this.#utilisateur(ligne) : null;
	}

	supprimer(id: number): void {
		this.base.prepare('DELETE FROM comptes WHERE id = ?').run(id);
	}

	/** Supprime les comptes jamais confirmés depuis plus de sept jours. Ils n'ont pas de
	 * profil côté API : rien à défaire ailleurs. */
	purgerNonConfirmes(): number {
		const limite = new Date(this.maintenant() - DELAI_CONFIRMATION_COMPTE_MS).toISOString();
		const resultat = this.base
			.prepare('DELETE FROM comptes WHERE confirme_le IS NULL AND cree_le < ?')
			.run(limite);
		return Number(resultat.changes);
	}

	lister(): CompteListe[] {
		const lignes = this.base
			.prepare(`SELECT ${COLONNES} FROM comptes ORDER BY username`)
			.all() as unknown as LigneCompte[];
		return lignes.map((ligne) => ({
			id: ligne.id,
			email: ligne.email,
			username: ligne.username,
			creeLe: ligne.cree_le,
			derniereConnexionLe: ligne.derniere_connexion_le,
			confirme: ligne.confirme_le !== null,
			admin: this.#estAdmin(ligne)
		}));
	}

	/** Seul un compte confirmé administre : sans cette condition, s'inscrire avec l'adresse
	 * de l'administrateur suffirait à le devenir. */
	#estAdmin(ligne: LigneCompte): boolean {
		if (ligne.confirme_le === null) return false;
		return (
			ligne.role === 'admin' ||
			(this.emailAdmin !== '' && normaliserEmail(this.emailAdmin) === ligne.email)
		);
	}

	#utilisateur(ligne: LigneCompte): Utilisateur {
		return new Utilisateur(
			ligne.id,
			ligne.email,
			ligne.username,
			ligne.role,
			this.#estAdmin(ligne),
			ligne.confirme_le !== null
		);
	}

	consultationsSeptJours(id: number): number {
		const debut = new Date(this.maintenant() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
		const ligne = this.base
			.prepare('SELECT COUNT(*) AS nombre FROM consultations WHERE compte_id = ? AND jour >= ?')
			.get(id, debut) as { nombre: number };
		return ligne.nombre;
	}
}
