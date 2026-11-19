import { defineEnvVars } from '@sveltejs/kit/env';

/** Une variable facultative : absente, elle vaut le défaut, vide comprise.
 *
 * Aucune n'est exigée au démarrage : l'image se construit sans environnement, et une
 * variable manquante se signale à l'endroit où elle sert (le client d'API, l'envoi
 * d'email), avec un message qui dit quoi renseigner. */
function facultative(defaut = '') {
	return (valeur: string | undefined) => valeur?.trim() || defaut;
}

export const variables = defineEnvVars({
	RSSRESUME_API_URL: {
		description: "Base de l'API de l'appli de résumé, ex. http://rssresume:8080",
		schema: facultative()
	},
	RSSRESUME_API_TOKEN: {
		description: "Jeton Bearer de l'API de résumé. Ne quitte jamais le serveur.",
		schema: facultative()
	},
	ADMIN_EMAIL: {
		description: "Adresse de l'administrateur : alertée à chaque inscription, et admin du site.",
		schema: facultative()
	},
	RESEND_API_KEY: {
		description: "Clé de l'API Resend ; absente, l'alerte d'inscription est seulement journalisée.",
		schema: facultative()
	},
	MAIL_FROM: {
		description: "Expéditeur de l'alerte d'inscription, sur un domaine vérifié chez Resend.",
		schema: facultative()
	},
	DATABASE_PATH: {
		description: 'Fichier SQLite des comptes du site.',
		schema: facultative('data/comptes.sqlite')
	}
});
