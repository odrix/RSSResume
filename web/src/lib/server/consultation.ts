/**
 * La lecture des résumés d'une personne : qui a le droit de voir quelle journée.
 *
 * L'API n'a qu'un jeton, celui du site : elle rend n'importe quelle journée à qui le porte.
 * Le contrôle « propriétaire ou administrateur » se fait donc ici, avant tout appel —
 * comme pour le relais audio —, et un refus ne se distingue pas d'une journée inexistante.
 */

import { urlSure, type ContenuJournee, type LienArticle, type Passage } from '#lib/journee.js';
import { ErreurApi, type ClientApiResume } from './api-resume.js';
import type { Utilisateur } from './comptes.js';
import { MOTIF_USERNAME } from './validation.js';
import type { DatabaseSync } from 'node:sqlite';

export const MOTIF_DATE = /^\d{4}-\d{2}-\d{2}$/;

export class ConsultationResumes {
	constructor(
		private readonly api: ClientApiResume,
		private readonly base: DatabaseSync | null = null,
		private readonly maintenant: () => number = Date.now
	) {}

	/** La journée, ou `null` — à rendre en 404 — si elle n'existe pas ou n'est pas à voir.
	 *
	 * `null` et non une erreur distincte pour qui n'y a pas droit : la page ne doit pas
	 * confirmer qu'un username existe. Les liens repassent par `urlSure` : l'API les a déjà
	 * filtrés, mais le site ne se fie pas à ce qu'il n'a pas vérifié lui-même. */
	async journee(utilisateur: Utilisateur, username: string, date: string): Promise<ContenuJournee | null> {
		if (!utilisateur.peutConsulter(username)) return null;
		if (!MOTIF_USERNAME.test(username) || !MOTIF_DATE.test(date)) return null;
		let contenu: ContenuJournee;
		try {
			contenu = await this.api.lireJournee(username, date);
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) return null;
			throw erreur;
		}
		return {
			...contenu,
			categories: contenu.categories.map((categorie) => ({
				...categorie,
				articles: categorie.articles.map(lienSur),
				a_surveiller: categorie.a_surveiller.map(lienSur)
			}))
		};
	}

	/** Le prochain passage, ou `null` si l'API ne répond pas : la page garde alors sa
	 * phrase sans heure plutôt que d'échouer pour un détail. */
	async passage(): Promise<Passage | null> {
		try {
			return await this.api.lirePassage();
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			return null;
		}
	}

	/** Compte une journée consultée une fois par compte et par jour calendaire. */
	noter(utilisateur: Utilisateur, date: string): void {
		if (!this.base) return;
		const jour = new Date(this.maintenant()).toISOString().slice(0, 10);
		this.base
			.prepare('INSERT OR IGNORE INTO consultations (compte_id, jour) VALUES (?, ?)')
			.run(utilisateur.id, jour);
	}
}

function lienSur(lien: LienArticle): LienArticle {
	return { ...lien, url: urlSure(lien.url) };
}
