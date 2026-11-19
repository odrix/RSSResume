import { isRedirect, isHttpError } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';
import { destinationSure, exigerAdmin, exigerConnexion } from './garde.js';
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
		const { comptes } = monter();
		const membre = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		const admin = await comptes.creer(EMAIL_ADMIN, 'chef', 'une phrase de passe');
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
});
