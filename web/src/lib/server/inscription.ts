/**
 * L'inscription : un compte ici, un profil là-bas, une alerte à l'administrateur.
 *
 * Deux bases qui ne partagent pas de transaction. L'ordre est choisi pour que l'échec le
 * plus probable — un username déjà pris côté API, une API indisponible — n'ait encore rien
 * écrit chez nous : on vérifie localement, on crée le profil, puis le compte. Si le compte
 * échoue malgré tout, le profil créé est supprimé plutôt que laissé orphelin.
 */

import { PROFIL_PAR_DEFAUT } from '#lib/profil.js';
import type { AlerteInscription } from './alerte.js';
import { ErreurApi, type ClientApiResume } from './api-resume.js';
import { CompteExistant, type Comptes, type Utilisateur } from './comptes.js';
import { erreurEmail, erreurMotDePasse, erreurUsername, normaliserEmail } from './validation.js';

export interface SaisieInscription {
	email: string;
	username: string;
	motDePasse: string;
	prenom: string;
	profil: string;
}

export type ChampInscription = keyof SaisieInscription | 'general';

export class ErreurInscription extends Error {
	constructor(
		readonly champ: ChampInscription,
		message: string
	) {
		super(message);
	}
}

export class Inscription {
	constructor(
		private readonly comptes: Comptes,
		private readonly api: ClientApiResume,
		private readonly alerte: AlerteInscription
	) {}

	async inscrire(saisie: SaisieInscription): Promise<Utilisateur> {
		const email = normaliserEmail(saisie.email);
		const verifications: [ChampInscription, string | null][] = [
			['email', erreurEmail(email)],
			['username', erreurUsername(saisie.username)],
			['motDePasse', erreurMotDePasse(saisie.motDePasse)]
		];
		for (const [champ, message] of verifications) {
			if (message) throw new ErreurInscription(champ, message);
		}

		const conflit = this.comptes.conflit(email, saisie.username);
		if (conflit) throw new ErreurInscription(conflit.champ, conflit.message);

		try {
			await this.api.creerProfil(saisie.username, {
				profil: saisie.profil.trim() || PROFIL_PAR_DEFAUT,
				stack: [],
				// Le digest part d'abord vers l'adresse du compte ; « Mon profil » permet d'en changer.
				email: [email],
				prenom: saisie.prenom.trim()
			});
		} catch (erreur) {
			throw this.#traduire(erreur);
		}

		let utilisateur: Utilisateur;
		try {
			utilisateur = await this.comptes.creer(email, saisie.username, saisie.motDePasse);
		} catch (erreur) {
			await this.api.supprimerProfil(saisie.username).catch((cause) => {
				console.error(`Profil ${saisie.username} orphelin, à supprimer côté API :`, cause);
			});
			if (erreur instanceof CompteExistant) throw new ErreurInscription(erreur.champ, erreur.message);
			throw erreur;
		}

		await this.alerte.envoyer({ username: utilisateur.username, email: utilisateur.email });
		return utilisateur;
	}

	#traduire(erreur: unknown): ErreurInscription {
		if (!(erreur instanceof ErreurApi)) throw erreur;
		if (erreur.statut === 409) return new ErreurInscription('username', "Ce nom d'utilisateur est pris.");
		if (erreur.statut === 422) return new ErreurInscription('profil', erreur.message);
		return new ErreurInscription('general', erreur.message);
	}
}
