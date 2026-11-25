/**
 * Ce qui permet de se connecter, changé depuis l'espace connecté : le mot de passe, et
 * l'adresse du compte.
 *
 * Les deux exigent le mot de passe actuel : une session laissée ouverte sur un poste
 * partagé ne doit pas suffire à s'approprier le compte. La nouvelle adresse, elle, n'est
 * appliquée qu'au clic sur le lien qu'elle reçoit — même règle qu'à l'inscription : on ne
 * se connecte qu'avec une adresse dont on a prouvé être le titulaire.
 *
 * Seul le compte du site change. Les adresses qui reçoivent le digest sont celles du
 * profil côté API, et se gèrent dans « Mon profil ».
 */

import { CompteExistant, type Comptes, type Utilisateur } from './comptes.js';
import type { Courrier } from './courrier.js';
import { ErreurConfirmation, LIEN_INVALIDE, lienConfirmation, type JetonsEmail } from './jetons-email.js';
import type { Sessions } from './sessions.js';
import { erreurEmail, erreurMotDePasse, normaliserEmail } from './validation.js';

export type ChampIdentifiants = 'motDePasseActuel' | 'nouveauMotDePasse' | 'email' | 'general';

export class ErreurIdentifiants extends Error {
	constructor(
		readonly champ: ChampIdentifiants,
		message: string
	) {
		super(message);
	}
}

export const MOT_DE_PASSE_ACTUEL_INCORRECT = 'Le mot de passe actuel est incorrect.';

export class Identifiants {
	constructor(
		private readonly comptes: Comptes,
		private readonly jetons: JetonsEmail,
		private readonly sessions: Sessions,
		private readonly courrier: Courrier
	) {}

	/** Change le mot de passe et ferme les autres sessions du compte ; `jetonSession` est
	 * celle d'où la personne agit, qui reste ouverte. */
	async changerMotDePasse(
		utilisateur: Utilisateur,
		actuel: string,
		nouveau: string,
		jetonSession: string | undefined
	): Promise<void> {
		await this.#verifierActuel(utilisateur, actuel);
		const refus = erreurMotDePasse(nouveau);
		if (refus) throw new ErreurIdentifiants('nouveauMotDePasse', refus);
		await this.comptes.changerMotDePasse(utilisateur.id, nouveau);
		this.sessions.fermerToutes(utilisateur.id, jetonSession);
	}

	/** Envoie le lien à la nouvelle adresse ; le compte garde l'ancienne jusqu'au clic. */
	async demanderChangementAdresse(
		utilisateur: Utilisateur,
		motDePasse: string,
		nouvelle: string,
		origine: string
	): Promise<string> {
		await this.#verifierActuel(utilisateur, motDePasse);
		const email = normaliserEmail(nouvelle);
		const refus = erreurEmail(email);
		if (refus) throw new ErreurIdentifiants('email', refus);
		if (email === utilisateur.email) {
			throw new ErreurIdentifiants('email', "C'est déjà l'adresse du compte.");
		}
		// L'inscription dit déjà qu'une adresse est prise : le taire ici ne cacherait rien.
		if (this.comptes.parEmail(email)) {
			throw new ErreurIdentifiants('email', new CompteExistant('email').message);
		}
		if (!this.courrier.disponible) {
			throw new ErreurIdentifiants(
				'general',
				"Impossible de changer d'adresse pour l'instant : l'email de confirmation ne peut pas partir."
			);
		}
		const jeton = this.jetons.emettre(utilisateur.id, email, 'adresse');
		if (!(await this.courrier.confirmerAdresse(utilisateur.username, email, lienConfirmation(origine, jeton)))) {
			this.jetons.revoquer(utilisateur.id, email, 'adresse');
			throw new ErreurIdentifiants(
				'general',
				"L'email de confirmation n'a pas pu être envoyé. Réessayez dans quelques minutes."
			);
		}
		return email;
	}

	/** Applique la nouvelle adresse, puis prévient l'ancienne. */
	async confirmerAdresse(jeton: string): Promise<{ ancienne: string; nouvelle: string }> {
		const lu = this.jetons.lire(jeton);
		const compte = lu?.objet === 'adresse' ? this.comptes.parId(lu.compteId) : null;
		if (!lu || !compte?.confirme) throw new ErreurConfirmation(LIEN_INVALIDE);
		if (compte.email === lu.email) {
			this.jetons.consommer(jeton);
			return { ancienne: lu.email, nouvelle: lu.email };
		}
		if (!this.jetons.consommer(jeton)) throw new ErreurConfirmation(LIEN_INVALIDE);
		try {
			this.comptes.changerEmail(compte.id, lu.email);
		} catch (erreur) {
			// Une inscription a pris l'adresse entre la demande et le clic.
			if (erreur instanceof CompteExistant) throw new ErreurConfirmation(erreur.message);
			throw erreur;
		}
		const envoye = await this.courrier.signalerChangementAdresse(compte.username, compte.email, lu.email);
		if (!envoye) console.error(`Avis de changement d'adresse de ${compte.username} non envoyé.`);
		return { ancienne: compte.email, nouvelle: lu.email };
	}

	async #verifierActuel(utilisateur: Utilisateur, motDePasse: string): Promise<void> {
		// Le même plafond qu'à la connexion : Argon2 ne travaille pas pour un texte démesuré.
		const verifie =
			motDePasse && motDePasse.length <= 1024
				? await this.comptes.authentifier(utilisateur.email, motDePasse)
				: null;
		if (verifie?.id !== utilisateur.id) {
			throw new ErreurIdentifiants('motDePasseActuel', MOT_DE_PASSE_ACTUEL_INCORRECT);
		}
	}
}
