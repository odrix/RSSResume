import type { Handle } from '@sveltejs/kit/hooks';
import { effacerCookieSession, poserCookieSession } from '#lib/server/cookie.js';
import { contexte } from '#lib/server/contexte.js';
import { postIntersiteInterdit } from '#lib/server/csrf.js';
import { COOKIE_SESSION } from '#lib/server/sessions.js';

/** Refuse les formulaires d'autres sites, charge la personne connectée, puis ajoute aux
 * réponses les en-têtes que la CSP de `vite.config.ts` ne couvre pas.
 *
 * Le refus vient en tête, avant toute lecture de session : c'est la protection CSRF que
 * SvelteKit n'applique plus (`csrf.trustedOrigins`), et elle doit tomber là où il la
 * faisait tomber, avant que quoi que ce soit ne s'exécute pour la requête. */
export const handle: Handle = async ({ event, resolve }) => {
	if (postIntersiteInterdit(event.request, event.url)) {
		return new Response(`Cross-site ${event.request.method} form submissions are forbidden`, {
			status: 403,
			headers: { 'content-type': 'text/plain; charset=utf-8' }
		});
	}
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
