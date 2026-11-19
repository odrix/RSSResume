/**
 * Le seul endroit où l'environnement est lu et les collaborateurs assemblés — l'équivalent
 * de `build_service()` dans l'appli de résumé. Les classes reçoivent leur configuration au
 * constructeur et ne lisent jamais l'environnement : c'est ce qui les rend testables.
 *
 * Assemblé à la première requête et non à l'import : `vite build` charge les modules
 * serveur sans environnement ni base de données.
 */

import {
	ADMIN_EMAIL,
	DATABASE_PATH,
	MAIL_FROM,
	RESEND_API_KEY,
	RSSRESUME_API_TOKEN,
	RSSRESUME_API_URL
} from '$app/env/private';
import { AlerteInscription } from './alerte.js';
import { ClientApiResume } from './api-resume.js';
import { ouvrirBase } from './base.js';
import { Comptes } from './comptes.js';
import { Inscription } from './inscription.js';
import { LimiteurTentatives } from './limiteur.js';
import { RelaisAudio } from './relais-audio.js';
import { Sessions } from './sessions.js';

const MINUTE_MS = 60_000;

export class Contexte {
	readonly api: ClientApiResume;
	readonly comptes: Comptes;
	readonly sessions: Sessions;
	readonly inscription: Inscription;
	readonly relaisAudio: RelaisAudio;
	/** Par adresse visée : freine qui s'acharne sur un compte, d'où qu'il vienne. */
	readonly limiteParEmail = new LimiteurTentatives(5, 15 * MINUTE_MS);
	/** Par IP : freine qui balaie les adresses. Plus large, une IP pouvant être partagée. */
	readonly limiteParIp = new LimiteurTentatives(30, 15 * MINUTE_MS);
	/** Les inscriptions réussies par IP : l'inscription est ouverte, pas illimitée. */
	readonly limiteInscriptions = new LimiteurTentatives(5, 60 * MINUTE_MS);

	constructor() {
		const base = ouvrirBase(DATABASE_PATH);
		this.api = new ClientApiResume({ baseUrl: RSSRESUME_API_URL, jeton: RSSRESUME_API_TOKEN });
		this.comptes = new Comptes(base, ADMIN_EMAIL);
		this.sessions = new Sessions(base, this.comptes);
		this.sessions.purgerExpirees();
		this.inscription = new Inscription(
			this.comptes,
			this.api,
			new AlerteInscription({
				cleApi: RESEND_API_KEY,
				expediteur: MAIL_FROM,
				destinataire: ADMIN_EMAIL
			})
		);
		this.relaisAudio = new RelaisAudio(this.api);
		if (!RSSRESUME_API_URL || !RSSRESUME_API_TOKEN) {
			console.warn("RSSRESUME_API_URL ou RSSRESUME_API_TOKEN manquante : l'API de résumé sera injoignable.");
		}
	}
}

let instance: Contexte | null = null;

export function contexte(): Contexte {
	instance ??= new Contexte();
	return instance;
}
