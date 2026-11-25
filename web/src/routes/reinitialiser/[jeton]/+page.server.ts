import { fail, redirect } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { effacerCookieSession } from '#lib/server/cookie.js';
import { ErreurConfirmation } from '#lib/server/jetons-email.js';
import { ErreurMotDePasse, LIEN_REINITIALISATION_INVALIDE } from '#lib/server/reinitialisation.js';
import type { Actions, PageServerLoad } from './$types';

/** Afficher la page ne consomme pas le lien : un antivirus de messagerie qui l'ouvre ne
 * doit pas le rendre inutilisable. Seul l'envoi du formulaire (POST) le consomme. */
export const load: PageServerLoad = ({ params }) => {
	const compte = contexte().reinitialisation.lire(params.jeton);
	return compte
		? { username: compte.username, invalide: null }
		: { username: null, invalide: LIEN_REINITIALISATION_INVALIDE };
};

export const actions: Actions = {
	default: async ({ params, request, cookies }) => {
		const motDePasse = String((await request.formData()).get('motDePasse') ?? '');
		try {
			await contexte().reinitialisation.reinitialiser(params.jeton, motDePasse);
		} catch (erreur) {
			if (erreur instanceof ErreurMotDePasse) return fail(422, { message: erreur.message, champ: 'motDePasse' });
			if (erreur instanceof ErreurConfirmation) return fail(400, { message: erreur.message, champ: null });
			throw erreur;
		}
		// Toutes les sessions du compte viennent d'être fermées, celle de ce navigateur comprise.
		effacerCookieSession(cookies);
		redirect(303, '/connexion?reinitialise=1');
	}
};
