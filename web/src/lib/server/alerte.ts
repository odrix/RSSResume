/**
 * L'email qui prévient l'administrateur d'une inscription, par l'API HTTP de Resend.
 *
 * Par HTTP et non SMTP pour la même raison que l'appli de résumé : le VPS filtre les ports
 * SMTP sortants. Par `fetch` et sans SDK : un seul appel POST ne justifie pas une dépendance.
 * Une alerte qui échoue ne fait jamais échouer l'inscription — elle se journalise.
 */

export interface OptionsAlerte {
	cleApi: string;
	expediteur: string;
	destinataire: string;
	fetch?: typeof fetch;
}

export interface Inscrit {
	username: string;
	email: string;
}

export class AlerteInscription {
	readonly #fetch: typeof fetch;

	constructor(private readonly options: OptionsAlerte) {
		this.#fetch = options.fetch ?? fetch;
	}

	get configuree(): boolean {
		const { cleApi, expediteur, destinataire } = this.options;
		return Boolean(cleApi && expediteur && destinataire);
	}

	/** Rend vrai si Resend a accepté l'envoi ; ne lève jamais. */
	async envoyer(inscrit: Inscrit): Promise<boolean> {
		if (!this.configuree) {
			console.warn(
				`Inscription de ${inscrit.username} <${inscrit.email}> : alerte non envoyée, ` +
					'RESEND_API_KEY, MAIL_FROM ou ADMIN_EMAIL manquante.'
			);
			return false;
		}
		try {
			const reponse = await this.#fetch('https://api.resend.com/emails', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${this.options.cleApi}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					from: this.options.expediteur,
					to: [this.options.destinataire],
					subject: `RSSResume : nouvelle inscription (${inscrit.username})`,
					text:
						`Un compte vient d'être créé sur le site RSSResume.\n\n` +
						`Nom d'utilisateur : ${inscrit.username}\n` +
						`Adresse : ${inscrit.email}\n` +
						`Date : ${new Date().toISOString()}\n`
				}),
				signal: AbortSignal.timeout(10_000)
			});
			if (!reponse.ok) {
				console.error(`Alerte d'inscription refusée par Resend (${reponse.status}) :`, await reponse.text());
				return false;
			}
			return true;
		} catch (erreur) {
			console.error("Alerte d'inscription non envoyée :", erreur);
			return false;
		}
	}
}
