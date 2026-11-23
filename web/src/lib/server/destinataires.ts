/**
 * Les adresses qui reçoivent le digest d'un profil.
 *
 * L'API ne reçoit que des adresses prouvées : celle du compte, confirmée à l'inscription,
 * et celles dont le titulaire a cliqué le lien reçu. Une adresse ajoutée dans « Mon profil »
 * attend ici, dans la base du site, jusqu'à ce clic ; sans cette étape, n'importe qui
 * pourrait abonner n'importe quelle boîte au digest. Retirer une adresse, en revanche,
 * ne demande rien à personne et vaut immédiatement.
 */

import type { DatabaseSync } from 'node:sqlite';
import type { Profil, ProfilSaisi } from '#lib/profil.js';
import { ErreurApi, type ClientApiResume } from './api-resume.js';
import type { Comptes, Utilisateur } from './comptes.js';
import type { Courrier } from './courrier.js';
import {
	ErreurConfirmation,
	LIEN_INVALIDE,
	lienConfirmation,
	type JetonsEmail
} from './jetons-email.js';
import type { LimiteurTentatives } from './limiteur.js';
import { erreurEmail, normaliserEmail } from './validation.js';

/** Au-delà, une liste d'attente n'est plus une liste de destinataires mais un envoi de masse. */
export const MAX_EN_ATTENTE = 10;

/** Une saisie refusée avant tout appel à l'API ; le message est affiché tel quel. */
export class ErreurDestinataire extends Error {}

export interface Enregistrement {
	profil: Profil;
	/** Les adresses qui viennent de recevoir un lien. */
	liensEnvoyes: string[];
	/** Toutes les adresses en attente après l'enregistrement. */
	enAttente: string[];
}

export class Destinataires {
	constructor(
		private readonly base: DatabaseSync,
		private readonly comptes: Comptes,
		private readonly jetons: JetonsEmail,
		private readonly api: ClientApiResume,
		private readonly courrier: Courrier,
		/** Les liens envoyés par compte : protège les boîtes des autres, pas le site. */
		private readonly limiteEnvois: LimiteurTentatives
	) {}

	enAttente(compteId: number): string[] {
		const lignes = this.base
			.prepare('SELECT email FROM destinataires_en_attente WHERE compte_id = ? ORDER BY email')
			.all(compteId) as { email: string }[];
		return lignes.map((ligne) => ligne.email);
	}

	/** Enregistre le profil : les adresses déjà prouvées partent à l'API, les nouvelles
	 * reçoivent un lien, celles qui ont disparu de la saisie sont retirées. */
	async enregistrerProfil(
		utilisateur: Utilisateur,
		saisie: ProfilSaisi,
		origine: string
	): Promise<Enregistrement> {
		const demandees = [...new Set(saisie.email.map(normaliserEmail))];
		for (const email of demandees) {
			const erreur = erreurEmail(email);
			if (erreur) throw new ErreurDestinataire(`${erreur} (${email})`);
		}

		let actuel: Profil | null = null;
		try {
			actuel = await this.api.lireProfil(utilisateur.username);
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi && erreur.introuvable)) throw erreur;
		}
		const prouvees = new Set([...(actuel?.email ?? []).map(normaliserEmail), utilisateur.email]);
		const directes = demandees.filter((email) => prouvees.has(email));
		const nouvelles = demandees.filter((email) => !prouvees.has(email));

		const dejaEnAttente = new Set(this.enAttente(utilisateur.id));
		const aEnvoyer = nouvelles.filter((email) => !dejaEnAttente.has(email));
		if (nouvelles.length > MAX_EN_ATTENTE) {
			throw new ErreurDestinataire(`Au plus ${MAX_EN_ATTENTE} adresses peuvent attendre leur confirmation.`);
		}
		if (aEnvoyer.length && !this.courrier.disponible) {
			throw new ErreurDestinataire(
				"Impossible d'ajouter une adresse pour l'instant : l'email de confirmation ne peut pas partir."
			);
		}
		const cle = String(utilisateur.id);
		if (aEnvoyer.length && !this.limiteEnvois.autorise(cle)) {
			throw new ErreurDestinataire("Trop d'adresses ajoutées récemment. Réessayez dans une heure.");
		}

		// Le formulaire n'édite ni les axes ni les catégories ; le PUT remplaçant tout le
		// document, les omettre effacerait ceux du gabarit au premier enregistrement.
		const corps = { ...saisie, axes: actuel?.axes, categories: actuel?.categories, email: directes };
		const profil = actuel
			? await this.api.modifierProfil(utilisateur.username, corps)
			: await this.api.creerProfil(utilisateur.username, corps);

		for (const email of dejaEnAttente) {
			if (!nouvelles.includes(email)) this.#retirer(utilisateur.id, email);
		}
		const liensEnvoyes: string[] = [];
		for (const email of aEnvoyer) {
			this.base
				.prepare('INSERT OR IGNORE INTO destinataires_en_attente (compte_id, email) VALUES (?, ?)')
				.run(utilisateur.id, email);
			const jeton = this.jetons.emettre(utilisateur.id, email, 'destinataire');
			this.limiteEnvois.noter(cle);
			if (
				await this.courrier.confirmerDestinataire(
					utilisateur.username,
					email,
					lienConfirmation(origine, jeton)
				)
			) {
				liensEnvoyes.push(email);
			}
		}
		return { profil, liensEnvoyes, enAttente: this.enAttente(utilisateur.id) };
	}

	/** Ajoute l'adresse au profil côté API. Le jeton n'est consommé qu'après : une API
	 * indisponible laisse le lien utilisable. */
	async confirmer(jeton: string): Promise<{ username: string; email: string }> {
		const lu = this.jetons.lire(jeton);
		const compte = lu?.objet === 'destinataire' ? this.comptes.parId(lu.compteId) : null;
		if (!lu || !compte?.confirme || !this.enAttente(compte.id).includes(lu.email)) {
			throw new ErreurConfirmation(LIEN_INVALIDE);
		}
		try {
			const profil = await this.api.lireProfil(compte.username);
			if (!profil.email.map(normaliserEmail).includes(lu.email)) {
				await this.api.modifierProfil(compte.username, { ...profil, email: [...profil.email, lu.email] });
			}
		} catch (erreur) {
			if (erreur instanceof ErreurApi) throw new ErreurConfirmation(erreur.message);
			throw erreur;
		}
		this.#retirer(compte.id, lu.email);
		return { username: compte.username, email: lu.email };
	}

	#retirer(compteId: number, email: string): void {
		this.base
			.prepare('DELETE FROM destinataires_en_attente WHERE compte_id = ? AND email = ?')
			.run(compteId, email);
		this.jetons.revoquer(compteId, email, 'destinataire');
	}
}
