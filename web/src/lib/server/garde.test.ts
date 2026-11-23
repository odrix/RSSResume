import { isRedirect, isHttpError } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';
import { destinationApresConnexion, destinationSure, exigerAdmin, exigerConnexion } from './garde.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';

function leve(fonction: () => unknown): unknown {
	try {
		fonction();
	} catch (lancee) {
		return lancee;
	}
	throw new Error("rien n'a été levé");
}

describe('gardes', () => {
	it('renvoie vers la connexion en retenant la page demandée', () => {
		const lancee = leve(() => exigerConnexion(null, new URL('http://site.test/profil?x=1')));
		expect(isRedirect(lancee)).toBe(true);
		expect(isRedirect(lancee) && lancee.location).toBe('/connexion?suite=%2Fprofil%3Fx%3D1');
	});

	it("cache l'administration aux membres par un 404", async () => {
		const { creerConfirme } = monter();
		const membre = await creerConfirme('moi@example.com', 'moi');
		const admin = await creerConfirme(EMAIL_ADMIN, 'chef');
		const lancee = leve(() => exigerAdmin(membre, new URL('http://site.test/admin')));
		expect(isHttpError(lancee, 404)).toBe(true);
		expect(exigerAdmin(admin, new URL('http://site.test/admin'))).toBe(admin);
	});

	it.each([
		['/profil', '/profil'],
		['/resumes/moi?x=1', '/resumes/moi?x=1'],
		[null, '/resumes'],
		['https://ailleurs.example', '/resumes'],
		['//ailleurs.example', '/resumes'],
		['/\\ailleurs.example', '/resumes'],
		['javascript:alert(1)', '/resumes']
	])('ne suit que les destinations locales (%s)', (suite, attendu) => {
		expect(destinationSure(suite)).toBe(attendu);
	});

	it('la première connexion mène au profil, les suivantes aux résumés, une suite explicite l’emporte', async () => {
		const { creerConfirme, comptes } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		// L'enchaînement de la page de connexion : noter, puis choisir la destination.
		expect(destinationApresConnexion(null, comptes.noterPremiereConnexion(moi.id))).toBe('/profil');
		expect(destinationApresConnexion(null, comptes.noterPremiereConnexion(moi.id))).toBe('/resumes');

		expect(destinationApresConnexion('/resumes/moi/2026-11-21', true)).toBe('/resumes/moi/2026-11-21');
		// Une suite forgée ne fait pas perdre la règle de la première connexion.
		expect(destinationApresConnexion('//ailleurs.example', true)).toBe('/profil');
	});
});
