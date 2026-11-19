/**
 * L'inscription, en deux temps : un compte en attente ici, puis — au clic sur le lien
 * reçu — le profil côté API et l'alerte à l'administrateur.
 *
 * Le profil n'est créé qu'à la confirmation parce que c'est lui qui fait partir le digest :
 * créé plus tôt, il enverrait chaque matin un email à une adresse que personne n'a prouvé
 * posséder. Jusque-là, le texte saisi attend dans le brouillon du compte.
 */

import { PROFIL_PAR_DEFAUT } from '#lib/profil.js';
import { ErreurApi, type ClientApiResume } from './api-resume.js';
import { CompteExistant, type Comptes, type Utilisateur } from './comptes.js';
import type { Courrier } from './courrier.js';
import {
	ErreurConfirmation,
	LIEN_INVALIDE,
	lienConfirmation,
	type JetonsEmail
} from './jetons-email.js';
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
		private readonly jetons: JetonsEmail,
		private readonly api: ClientApiResume,
		private readonly courrier: Courrier
	) {}

	/** Crée le compte en attente et envoie le lien. `origine` est l'adresse publique du site,
	 * qui préfixe le lien. */
	async inscrire(saisie: SaisieInscription, origine: string): Promise<Utilisateur> {
		const email = normaliserEmail(saisie.email);
		const verifications: [ChampInscription, string | null][] = [
			['email', erreurEmail(email)],
			['username', erreurUsername(saisie.username)],
			['motDePasse', erreurMotDePasse(saisie.motDePasse)]
		];
		for (const [champ, message] of verifications) {
			if (message) throw new ErreurInscription(champ, message);
		}
		if (!this.courrier.disponible) {
			console.error("Inscription refusée : aucun transport d'email configuré (RESEND_API_KEY, MAIL_FROM).");
			throw new ErreurInscription(
				'general',
				"Les inscriptions sont momentanément fermées : l'email de confirmation ne peut pas partir."
			);
		}

		// À la volée : un compte abandonné depuis sept jours libère son adresse et son username.
		this.comptes.purgerNonConfirmes();
		const conflit = this.comptes.conflit(email, saisie.username);
		if (conflit) throw new ErreurInscription(conflit.champ, conflit.message);

		let utilisateur: Utilisateur;
		try {
			utilisateur = await this.comptes.creer(email, saisie.username, saisie.motDePasse, {
				profil: saisie.profil.trim(),
				prenom: saisie.prenom.trim()
			});
		} catch (erreur) {
			if (erreur instanceof CompteExistant) throw new ErreurInscription(erreur.champ, erreur.message);
			throw erreur;
		}

		if (!(await this.#envoyerLien(utilisateur, origine))) {
			// Un compte dont le lien n'est jamais parti ne pourrait pas être activé.
			this.comptes.supprimer(utilisateur.id);
			throw new ErreurInscription(
				'general',
				"L'email de confirmation n'a pas pu être envoyé. Réessayez dans quelques minutes."
			);
		}
		return utilisateur;
	}

	/** Renvoie un lien à un compte en attente. Silencieux dans tous les cas : la réponse ne
	 * doit pas dire si l'adresse a un compte. */
	async renvoyer(email: string, origine: string): Promise<void> {
		const utilisateur = this.comptes.parEmail(email);
		if (!utilisateur || utilisateur.confirme) return;
		await this.#envoyerLien(utilisateur, origine);
	}

	/** Crée le profil, confirme le compte, prévient l'administrateur. Le jeton n'est
	 * consommé qu'une fois le profil créé : une API indisponible laisse le lien utilisable. */
	async confirmer(jeton: string): Promise<Utilisateur> {
		const lu = this.jetons.lire(jeton);
		const compte = lu?.objet === 'inscription' ? this.comptes.parId(lu.compteId) : null;
		if (!lu || !compte || compte.email !== lu.email) throw new ErreurConfirmation(LIEN_INVALIDE);
		if (compte.confirme) {
			this.jetons.consommer(jeton);
			return compte;
		}

		const brouillon = this.comptes.brouillon(compte.id);
		try {
			await this.api.creerProfil(compte.username, {
				profil: brouillon.profil || PROFIL_PAR_DEFAUT,
				stack: [],
				// L'adresse du compte vient d'être prouvée : c'est le premier destinataire.
				email: [compte.email],
				prenom: brouillon.prenom
			});
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			if (erreur.statut === 409) {
				console.error(`Confirmation de ${compte.username} : le profil existe déjà côté API.`);
				throw new ErreurConfirmation(
					"Ce nom d'utilisateur est déjà utilisé par le service de résumé. Contactez l'administrateur."
				);
			}
			throw new ErreurConfirmation(erreur.message);
		}

		this.comptes.confirmer(compte.id);
		this.jetons.consommer(jeton);
		await this.courrier.alerterAdmin({ username: compte.username, email: compte.email });
		return this.comptes.parId(compte.id)!;
	}

	#envoyerLien(utilisateur: Utilisateur, origine: string): Promise<boolean> {
		const jeton = this.jetons.emettre(utilisateur.id, utilisateur.email, 'inscription');
		return this.courrier.confirmerInscription(
			{ username: utilisateur.username, email: utilisateur.email },
			lienConfirmation(origine, jeton)
		);
	}
}
