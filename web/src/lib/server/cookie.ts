/**
 * Le cookie de session, posé au même endroit pour la connexion, l'inscription et la
 * prolongation : ses attributs de sécurité ne doivent pas dépendre de l'appelant.
 */

import type { Cookies } from '@sveltejs/kit';
import { COOKIE_SESSION } from './sessions.js';

export function poserCookieSession(cookies: Cookies, jeton: string, expireLe: Date): void {
	// `secure` est déjà le défaut de SvelteKit hors de http://localhost ; il est écrit ici
	// pour qu'on n'ait pas à le savoir. `lax` laisse suivre un lien venu d'un email.
	cookies.set(COOKIE_SESSION, jeton, {
		path: '/',
		httpOnly: true,
		secure: true,
		sameSite: 'lax',
		expires: expireLe
	});
}

export function effacerCookieSession(cookies: Cookies): void {
	cookies.delete(COOKIE_SESSION, { path: '/' });
}
