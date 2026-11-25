/**
 * Le mot de passe oublié : un lien à usage unique, envoyé à l'adresse du compte, qui
 * permet d'en choisir un nouveau.
 *
 * La demande ne dit jamais si l'adresse a un compte : la page répond la même chose, et
 * l'email part sans être attendu, pour que le temps de réponse ne le dise pas non plus.
 * Le lien est un jeton de `jetons-email.ts` : même empreinte en base, même usage unique,
 * une heure au lieu de vingt-quatre.
 */

import type { Comptes, Utilisateur } from './comptes.js';
import type { Courrier } from './courrier.js';
import {
	DUREE_REINITIALISATION_MS,
	ErreurConfirmation,
	lienReinitialisation,
	type JetonsEmail
} from './jetons-email.js';
import type { Sessions } from './sessions.js';
import { erreurMotDePasse, normaliserEmail } from './validation.js';

export const LIEN_REINITIALISATION_INVALIDE =
	'Ce lien de réinitialisation est invalide, expiré ou déjà utilisé. Demandez-en un nouveau.';

/** Le nouveau mot de passe ne respecte pas les règles : le lien reste utilisable. */
export class ErreurMotDePasse extends Error {}

export class Reinitialisation {
	constructor(
		private readonly comptes: Comptes,
		private readonly jetons: JetonsEmail,
		private readonly sessions: Sessions,
		private readonly courrier: Courrier
	) {}

	/** Envoie un lien si l'adresse a un compte confirmé ; ne rend rien dans tous les cas.
	 *
	 * Un compte en attente n'en reçoit pas : il n'a pas encore prouvé son adresse, et c'est
	 * « Renvoyer le lien » qui le débloque. Tout le travail est différé — l'écriture du jeton
	 * comprise, synchrone — : sinon une adresse connue répondrait plus lentement qu'une
	 * inconnue. Une erreur différée est journalisée, jamais laissée en rejet non géré, qui
	 * arrêterait Node. */
	demander(email: string, origine: string): void {
		const utilisateur = this.comptes.parEmail(normaliserEmail(email));
		if (!utilisateur?.confirme) return;
		setImmediate(() => {
			this.#envoyer(utilisateur, origine).catch((erreur) => {
				console.error(`Lien de réinitialisation de ${utilisateur.username} non envoyé :`, erreur);
			});
		});
	}

	/** Le compte que le lien permet de réinitialiser, sans le consommer : la page s'affiche
	 * avant que la personne ait choisi son mot de passe. */
	lire(jeton: string): Utilisateur | null {
		const lu = this.jetons.lire(jeton);
		if (lu?.objet !== 'reinitialisation') return null;
		const compte = this.comptes.parId(lu.compteId);
		// Une adresse changée depuis l'envoi rend le lien caduc : il visait l'ancienne boîte.
		if (!compte?.confirme || compte.email !== lu.email) return null;
		return compte;
	}

	/** Fixe le nouveau mot de passe et ferme toutes les sessions du compte : celui qui
	 * réinitialise reprend la main, une session ouverte par un autre ne survit pas — ni un
	 * lien de réinitialisation ou de changement d'adresse encore en circulation. */
	async reinitialiser(jeton: string, motDePasse: string): Promise<Utilisateur> {
		const compte = this.lire(jeton);
		if (!compte) throw new ErreurConfirmation(LIEN_REINITIALISATION_INVALIDE);
		const refus = erreurMotDePasse(motDePasse);
		if (refus) throw new ErreurMotDePasse(refus);
		if (!this.jetons.consommer(jeton)) throw new ErreurConfirmation(LIEN_REINITIALISATION_INVALIDE);
		await this.comptes.changerMotDePasse(compte.id, motDePasse);
		this.sessions.fermerToutes(compte.id);
		this.jetons.revoquerTous(compte.id, 'reinitialisation', 'adresse');
		return compte;
	}

	async #envoyer(utilisateur: Utilisateur, origine: string): Promise<void> {
		const jeton = this.jetons.emettre(
			utilisateur.id,
			utilisateur.email,
			'reinitialisation',
			DUREE_REINITIALISATION_MS
		);
		const envoye = await this.courrier.reinitialiserMotDePasse(
			{ username: utilisateur.username, email: utilisateur.email },
			lienReinitialisation(origine, jeton)
		);
		if (!envoye) console.error(`Lien de réinitialisation de ${utilisateur.username} non envoyé.`);
	}
}
