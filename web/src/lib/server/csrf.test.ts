import { describe, expect, it } from 'vitest';
import { postIntersiteInterdit } from './csrf.js';

/* La protection CSRF de SvelteKit est levée (`csrf.trustedOrigins: ['*']`) et réécrite ici :
 * chaque cas que SvelteKit refusait doit l'être encore, et seule la route du désabonnement
 * en un clic doit s'ouvrir. */

const SITE = 'https://site.test';

function requete(
	chemin: string,
	options: { methode?: string; origine?: string | null; type?: string | null } = {}
): [Request, URL] {
	const url = new URL(chemin, SITE);
	const entetes = new Headers();
	const type = options.type === undefined ? 'application/x-www-form-urlencoded' : options.type;
	if (type) entetes.set('content-type', type);
	if (options.origine) entetes.set('origin', options.origine);
	const methode = options.methode ?? 'POST';
	const corps = methode === 'GET' || methode === 'HEAD' ? undefined : 'a=1';
	return [new Request(url, { method: methode, headers: entetes, body: corps }), url];
}

describe('postIntersiteInterdit', () => {
	it("refuse un formulaire posté vers le profil depuis un autre site, ou sans origine", () => {
		for (const origine of ['https://ailleurs.test', null, 'null']) {
			expect(postIntersiteInterdit(...requete('/profil', { origine }))).toBe(true);
		}
	});

	it('refuse chaque type de corps et chaque méthode que SvelteKit protégeait', () => {
		for (const type of [
			'application/x-www-form-urlencoded',
			'multipart/form-data; boundary=x',
			'text/plain;charset=UTF-8',
			'Application/X-WWW-Form-Urlencoded',
			'application/x-sveltekit-formdata',
			null
		]) {
			expect(postIntersiteInterdit(...requete('/connexion', { type, origine: 'https://ailleurs.test' }))).toBe(true);
		}
		for (const methode of ['PUT', 'PATCH', 'DELETE']) {
			expect(postIntersiteInterdit(...requete('/profil', { methode, origine: 'https://ailleurs.test' }))).toBe(true);
		}
	});

	it('laisse passer le désabonnement en un clic, qui arrive sans origine', () => {
		expect(postIntersiteInterdit(...requete('/desabonnement/v1.abc.def', { origine: null }))).toBe(false);
		expect(postIntersiteInterdit(...requete('/desabonnement/v1.abc.def', { origine: 'https://mail.test' }))).toBe(
			false
		);
	});

	it("n'ouvre que le POST de cette route, et rien autour d'elle", () => {
		const ailleurs = { origine: 'https://ailleurs.test' };
		expect(postIntersiteInterdit(...requete('/desabonnement/v1.abc/autre', ailleurs))).toBe(true);
		expect(postIntersiteInterdit(...requete('/desabonnement', ailleurs))).toBe(true);
		expect(postIntersiteInterdit(...requete('/x/desabonnement/abc', ailleurs))).toBe(true);
		expect(postIntersiteInterdit(...requete('/desabonnement/abc', { ...ailleurs, methode: 'DELETE' }))).toBe(true);
	});

	it('garde la protection sur la page de vote, qui ne reçoit que son propre formulaire', () => {
		for (const origine of ['https://ailleurs.test', null]) {
			expect(postIntersiteInterdit(...requete('/retour/v1.abc.2026-11-22.def', { origine }))).toBe(true);
		}
		expect(postIntersiteInterdit(...requete('/retour/v1.abc.2026-11-22.def', { origine: SITE }))).toBe(false);
	});

	it('laisse passer la même origine, les lectures et le JSON', () => {
		expect(postIntersiteInterdit(...requete('/profil', { origine: SITE }))).toBe(false);
		expect(postIntersiteInterdit(...requete('/profil', { methode: 'GET', origine: null, type: null }))).toBe(false);
		expect(
			postIntersiteInterdit(...requete('/profil', { origine: 'https://ailleurs.test', type: 'application/json' }))
		).toBe(false);
	});
});
