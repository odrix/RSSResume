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
import { ClientApiResume } from './api-resume.js';
import { ouvrirBase } from './base.js';
import { Comptes } from './comptes.js';
import { ConsultationResumes } from './consultation.js';
import { CourrierAbsent, CourrierJournal, CourrierResend, type Courrier } from './courrier.js';
import { Destinataires } from './destinataires.js';
import { Inscription } from './inscription.js';
import { JetonsEmail } from './jetons-email.js';
import { LimiteurTentatives } from './limiteur.js';
import { RelaisAudio } from './relais-audio.js';
import { Sessions } from './sessions.js';

const MINUTE_MS = 60_000;

export class Contexte {
	readonly api: ClientApiResume;
	readonly comptes: Comptes;
	readonly sessions: Sessions;
	readonly jetons: JetonsEmail;
	readonly inscription: Inscription;
	readonly destinataires: Destinataires;
	readonly relaisAudio: RelaisAudio;
	readonly consultation: ConsultationResumes;
	/** Par adresse visée : freine qui s'acharne sur un compte, d'où qu'il vienne. */
	readonly limiteParEmail = new LimiteurTentatives(5, 15 * MINUTE_MS);
	/** Par IP : freine qui balaie les adresses. Plus large, une IP pouvant être partagée. */
	readonly limiteParIp = new LimiteurTentatives(30, 15 * MINUTE_MS);
	/** Les inscriptions par IP : l'inscription est ouverte, pas illimitée. */
	readonly limiteInscriptions = new LimiteurTentatives(5, 60 * MINUTE_MS);
	/** Les renvois de lien par adresse et par IP : chacun fait partir un email. */
	readonly limiteRenvoisParEmail = new LimiteurTentatives(3, 60 * MINUTE_MS);
	readonly limiteRenvoisParIp = new LimiteurTentatives(10, 60 * MINUTE_MS);

	constructor() {
		const base = ouvrirBase(DATABASE_PATH);
		const courrier = choisirCourrier();
		this.api = new ClientApiResume({ baseUrl: RSSRESUME_API_URL, jeton: RSSRESUME_API_TOKEN });
		this.comptes = new Comptes(base, ADMIN_EMAIL);
		this.sessions = new Sessions(base, this.comptes);
		this.jetons = new JetonsEmail(base);
		this.inscription = new Inscription(this.comptes, this.jetons, this.api, courrier);
		this.destinataires = new Destinataires(
			base,
			this.comptes,
			this.jetons,
			this.api,
			courrier,
			new LimiteurTentatives(10, 60 * MINUTE_MS)
		);
		this.relaisAudio = new RelaisAudio(this.api);
		this.consultation = new ConsultationResumes(this.api);

		this.sessions.purgerExpirees();
		this.jetons.purgerExpires();
		const purges = this.comptes.purgerNonConfirmes();
		if (purges) console.info(`${purges} compte(s) jamais confirmé(s) supprimé(s).`);
		if (!RSSRESUME_API_URL || !RSSRESUME_API_TOKEN) {
			console.warn("RSSRESUME_API_URL ou RSSRESUME_API_TOKEN manquante : l'API de résumé sera injoignable.");
		}
	}
}

/** Resend s'il est configuré. Sinon, en développement, la console ; en production, rien —
 * et les inscriptions sont refusées plutôt que de créer des comptes impossibles à activer. */
function choisirCourrier(): Courrier {
	if (RESEND_API_KEY && MAIL_FROM) {
		return new CourrierResend({ cleApi: RESEND_API_KEY, expediteur: MAIL_FROM, emailAdmin: ADMIN_EMAIL });
	}
	if (process.env.NODE_ENV !== 'production') {
		console.warn('RESEND_API_KEY ou MAIL_FROM absente : les emails, liens compris, vont dans la console.');
		return new CourrierJournal(ADMIN_EMAIL);
	}
	console.error('RESEND_API_KEY ou MAIL_FROM absente en production : inscriptions fermées.');
	return new CourrierAbsent(ADMIN_EMAIL);
}

let instance: Contexte | null = null;

export function contexte(): Contexte {
	instance ??= new Contexte();
	return instance;
}
