import type { Handle } from '@sveltejs/kit/hooks';
import { effacerCookieSession, poserCookieSession } from '#lib/server/cookie.js';
import { contexte } from '#lib/server/contexte.js';
import { COOKIE_SESSION } from '#lib/server/sessions.js';

/** Charge la personne connectée, puis ajoute aux réponses les en-têtes que la CSP de
 * `vite.config.ts` ne couvre pas. */
export const handle: Handle = async ({ event, resolve }) => {
	event.locals.utilisateur = null;
	const jeton = event.cookies.get(COOKIE_SESSION);
	if (jeton) {
		const session = contexte().sessions.valider(jeton);
		if (!session) {
			effacerCookieSession(event.cookies);
		} else {
			event.locals.utilisateur = session.utilisateur;
			if (session.prolongee) poserCookieSession(event.cookies, jeton, session.expireLe);
		}
	}

	const reponse = await resolve(event);
	reponse.headers.set('x-content-type-options', 'nosniff');
	reponse.headers.set('referrer-policy', 'same-origin');
	reponse.headers.set('x-frame-options', 'DENY');
	return reponse;
};
