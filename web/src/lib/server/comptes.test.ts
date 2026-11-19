import { describe, expect, it } from 'vitest';
import { ouvrirBase } from './base.js';
import { CompteExistant, Comptes, HacheurMotDePasse } from './comptes.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';

describe('Comptes', () => {
	it("authentifie avec le bon mot de passe, quelle que soit la casse de l'adresse", async () => {
		const { comptes } = monter();
		const cree = await comptes.creer('Moi@Example.com', 'moi', 'une phrase de passe');
		expect(cree.email).toBe('moi@example.com');
		expect((await comptes.authentifier('MOI@example.com', 'une phrase de passe'))?.id).toBe(cree.id);
		expect(await comptes.authentifier('moi@example.com', 'mauvais mot de passe')).toBeNull();
		expect(await comptes.authentifier('inconnu@example.com', 'une phrase de passe')).toBeNull();
	});

	it("signale l'email ou le username déjà pris", async () => {
		const { comptes } = monter();
		await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		expect(comptes.conflit('MOI@example.com', 'autre')?.champ).toBe('email');
		expect(comptes.conflit('autre@example.com', 'moi')?.champ).toBe('username');
		expect(comptes.conflit('autre@example.com', 'autre')).toBeNull();
		await expect(comptes.creer('autre@example.com', 'moi', 'une phrase de passe')).rejects.toBeInstanceOf(
			CompteExistant
		);
	});

	it("fait administrateur l'adresse de ADMIN_EMAIL, ou le rôle admin", async () => {
		const { base, comptes } = monter();
		const admin = await comptes.creer(EMAIL_ADMIN.toUpperCase(), 'chef', 'une phrase de passe');
		const membre = await comptes.creer('membre@example.com', 'membre', 'une phrase de passe');
		expect(admin.admin).toBe(true);
		expect(membre.admin).toBe(false);

		expect(comptes.lister().map((c) => [c.username, c.admin])).toEqual([
			['chef', true],
			['membre', false]
		]);

		base.prepare("UPDATE comptes SET role = 'admin' WHERE id = ?").run(membre.id);
		expect(comptes.parId(membre.id)?.admin).toBe(true);
	});

	it("ne fait personne administrateur quand ADMIN_EMAIL est vide", async () => {
		const comptes = new Comptes(ouvrirBase(':memory:'), '');
		const u = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		expect(u.admin).toBe(false);
	});

	it('contrôle la consultation : le propriétaire ou l’administrateur', async () => {
		const { comptes } = monter();
		const admin = await comptes.creer(EMAIL_ADMIN, 'chef', 'une phrase de passe');
		const moi = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		expect(moi.peutConsulter('moi')).toBe(true);
		expect(moi.peutConsulter('chef')).toBe(false);
		expect(admin.peutConsulter('moi')).toBe(true);
	});
});

describe('HacheurMotDePasse', () => {
	it('hache en Argon2id, jamais en clair', async () => {
		const hacheur = new HacheurMotDePasse();
		const empreinte = await hacheur.hacher('une phrase de passe');
		expect(empreinte).toMatch(/^\$argon2id\$/);
		expect(empreinte).not.toContain('une phrase de passe');
		expect(await hacheur.verifier(empreinte, 'une phrase de passe')).toBe(true);
		expect(await hacheur.verifier(empreinte, 'une autre phrase')).toBe(false);
		expect(await hacheur.verifier('pas une empreinte', 'x')).toBe(false);
	});
});
