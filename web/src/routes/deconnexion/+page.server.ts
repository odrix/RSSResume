import { redirect } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { effacerCookieSession } from '#lib/server/cookie.js';
import { COOKIE_SESSION } from '#lib/server/sessions.js';
import type { Actions, PageServerLoad } from './$types';

/** Pas de déconnexion par GET : un lien ou une image piégée ne doit pas pouvoir la provoquer. */
export const load: PageServerLoad = () => {
	redirect(303, '/');
};

export const actions: Actions = {
	default: ({ cookies }) => {
		const jeton = cookies.get(COOKIE_SESSION);
		if (jeton) contexte().sessions.fermer(jeton);
		effacerCookieSession(cookies);
		redirect(303, '/connexion');
	}
};
