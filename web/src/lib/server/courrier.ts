/**
 * Les emails du site : confirmer une adresse, prévenir l'administrateur.
 *
 * Le modèle est celui de `rssresume/llm/base.py` : la classe de base porte les messages,
 * c'est-à-dire ce que le site a à dire ; les sous-classes ne disent que comment ça part.
 * Trois transports, choisis dans `contexte.ts` :
 *
 * - `CourrierResend` : l'API HTTP de Resend, par `fetch` et sans SDK. HTTP et non SMTP
 *   parce que le VPS filtre les ports SMTP sortants ;
 * - `CourrierJournal` : en développement sans clé, le message — lien compris — va dans la
 *   console, de quoi tester l'inscription sans compte Resend ;
 * - `CourrierAbsent` : en production sans clé. Rien ne part, et `disponible` est faux : une
 *   inscription dont le lien de confirmation ne peut pas partir est refusée d'emblée.
 */

export interface Inscrit {
	username: string;
	email: string;
}

export abstract class Courrier {
	constructor(
		/** `ADMIN_EMAIL` ; vide, l'alerte d'inscription n'est que journalisée. */
		protected readonly emailAdmin: string
	) {}

	/** Faux quand aucun email ne peut partir : les liens de confirmation non plus. */
	abstract get disponible(): boolean;

	/** Envoie, et rend vrai si le message est accepté. Ne lève jamais. */
	protected abstract transmettre(destinataire: string, sujet: string, texte: string): Promise<boolean>;

	confirmerInscription(inscrit: Inscrit, lien: string): Promise<boolean> {
		return this.transmettre(
			inscrit.email,
			'RSSResume : confirmez votre adresse',
			`Bonjour,\n\n` +
				`Un compte « ${inscrit.username} » vient d'être créé sur RSSResume avec cette adresse.\n` +
				`Pour l'activer, ouvrez ce lien dans les 24 heures :\n\n${lien}\n\n` +
				`Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message : ` +
				`le compte sera supprimé dans sept jours.\n`
		);
	}

	confirmerDestinataire(username: string, email: string, lien: string): Promise<boolean> {
		return this.transmettre(
			email,
			'RSSResume : confirmez cette adresse de réception',
			`Bonjour,\n\n` +
				`Le compte RSSResume « ${username} » souhaite envoyer son résumé quotidien à cette adresse.\n` +
				`Pour l'accepter, ouvrez ce lien dans les 24 heures :\n\n${lien}\n\n` +
				`Sans confirmation, aucun email ne vous sera envoyé.\n`
		);
	}

	/** Part à la confirmation, pas à l'inscription : l'administrateur n'apprend que les
	 * comptes dont l'adresse est réelle. */
	async alerterAdmin(inscrit: Inscrit): Promise<boolean> {
		if (!this.emailAdmin) {
			console.warn(`Compte ${inscrit.username} <${inscrit.email}> confirmé ; ADMIN_EMAIL vide, pas d'alerte.`);
			return false;
		}
		return this.transmettre(
			this.emailAdmin,
			`RSSResume : nouvelle inscription (${inscrit.username})`,
			`Un compte vient d'être confirmé sur le site RSSResume.\n\n` +
				`Nom d'utilisateur : ${inscrit.username}\n` +
				`Adresse : ${inscrit.email}\n` +
				`Date : ${new Date().toISOString()}\n`
		);
	}
}

export interface OptionsResend {
	cleApi: string;
	expediteur: string;
	emailAdmin: string;
	fetch?: typeof fetch;
}

export class CourrierResend extends Courrier {
	readonly #cleApi: string;
	readonly #expediteur: string;
	readonly #fetch: typeof fetch;

	constructor(options: OptionsResend) {
		super(options.emailAdmin);
		this.#cleApi = options.cleApi;
		this.#expediteur = options.expediteur;
		this.#fetch = options.fetch ?? fetch;
	}

	get disponible(): boolean {
		return true;
	}

	protected async transmettre(destinataire: string, sujet: string, texte: string): Promise<boolean> {
		try {
			const reponse = await this.#fetch('https://api.resend.com/emails', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${this.#cleApi}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ from: this.#expediteur, to: [destinataire], subject: sujet, text: texte }),
				signal: AbortSignal.timeout(10_000)
			});
			if (!reponse.ok) {
				console.error(`Email « ${sujet} » refusé par Resend (${reponse.status}) :`, await reponse.text());
				return false;
			}
			return true;
		} catch (erreur) {
			console.error(`Email « ${sujet} » non envoyé :`, erreur);
			return false;
		}
	}
}

export class CourrierJournal extends Courrier {
	/** Les messages « envoyés », pour les tests. */
	readonly envoyes: { destinataire: string; sujet: string; texte: string }[] = [];

	constructor(
		emailAdmin: string,
		/** Faux dans les tests, qui lisent `envoyes` plutôt que la console. */
		private readonly journaliser = true
	) {
		super(emailAdmin);
	}

	get disponible(): boolean {
		return true;
	}

	protected async transmettre(destinataire: string, sujet: string, texte: string): Promise<boolean> {
		this.envoyes.push({ destinataire, sujet, texte });
		if (this.journaliser) console.info(`[email non envoyé — RESEND_API_KEY absente] À : ${destinataire}\n${sujet}\n\n${texte}`);
		return true;
	}
}

export class CourrierAbsent extends Courrier {
	get disponible(): boolean {
		return false;
	}

	protected async transmettre(destinataire: string, sujet: string): Promise<boolean> {
		console.error(
			`Email « ${sujet} » à ${destinataire} impossible : RESEND_API_KEY ou MAIL_FROM manquante en production.`
		);
		return false;
	}
}
