/**
 * Les gardes des pages : qui doit être connecté, qui doit être administrateur.
 */

import { error, redirect } from '@sveltejs/kit';
import type { Utilisateur } from './comptes.js';

/** Renvoie vers la connexion, en retenant la page demandée pour y revenir ensuite. */
export function exigerConnexion(utilisateur: Utilisateur | null, url: URL): Utilisateur {
	if (!utilisateur) {
		redirect(303, `/connexion?suite=${encodeURIComponent(url.pathname + url.search)}`);
	}
	return utilisateur;
}

export function exigerAdmin(utilisateur: Utilisateur | null, url: URL): Utilisateur {
	const connecte = exigerConnexion(utilisateur, url);
	// 404 : la page d'administration n'a pas à s'annoncer à qui n'y a pas droit.
	if (!connecte.admin) error(404, 'Page introuvable');
	return connecte;
}

/** Une destination de retour n'est suivie que si elle reste sur le site : un `suite`
 * forgé ne doit pas faire de la page de connexion une redirection ouverte. */
export function destinationSure(suite: string | null, defaut = '/resumes'): string {
	if (!suite || !suite.startsWith('/') || suite.startsWith('//') || suite.startsWith('/\\')) {
		return defaut;
	}
	return suite;
}

/** Après la connexion : la première mène au profil, que la personne relise ce qui
 * décidera de ses articles plutôt qu'une liste de résumés encore vide.
 *
 * Une page demandée explicitement l'emporte, et ne consomme pas la première connexion :
 * le lien des résumés dans l'email de bienvenue passe par `?suite=/resumes`, et la noter
 * là priverait la personne de son profil pour toujours. `noterPremiere` n'est donc
 * appelée que si la connexion mène effectivement au profil, ou pourrait y mener. */
export function destinationApresConnexion(suite: string | null, noterPremiere: () => boolean): string {
	const demandee = destinationSure(suite, '');
	if (demandee && new URL(demandee, 'http://site.invalid').pathname !== '/profil') return demandee;
	const premiere = noterPremiere();
	return demandee || (premiere ? '/profil' : '/resumes');
}
