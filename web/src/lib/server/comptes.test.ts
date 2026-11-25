import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import { migrer, ouvrirBase } from './base.js';
import { CompteExistant, Comptes, DELAI_CONFIRMATION_COMPTE_MS, HacheurMotDePasse } from './comptes.js';
import { EMAIL_ADMIN, FauxHacheur, monter } from './outils-test.js';

describe('Comptes', () => {
	it("authentifie avec le bon mot de passe, quelle que soit la casse de l'adresse", async () => {
		const { comptes } = monter();
		const cree = await comptes.creer('Moi@Example.com', 'moi', 'une phrase de passe');
		expect(cree.email).toBe('moi@example.com');
		expect((await comptes.authentifier('MOI@example.com', 'une phrase de passe'))?.id).toBe(cree.id);
		expect(await comptes.authentifier('moi@example.com', 'mauvais mot de passe')).toBeNull();
		expect(await comptes.authentifier('inconnu@example.com', 'une phrase de passe')).toBeNull();
	});

	it('crée un compte en attente, avec son brouillon, que la confirmation efface', async () => {
		const { comptes } = monter();
		const gabarit = {
			metier: 'rssi',
			libelle: 'RSSI',
			stack: ['Traefik', { nom: 'Keycloak', alias: ['RH-SSO'] }],
			securite: 'exploitant' as const,
			axes: [{ slug: 'menaces', libelle: 'Menaces', description: 'campagnes actives' }],
			categories: ['Cybersécurité']
		};
		const cree = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe', {
			profil: 'RSSI',
			prenom: 'Adrien',
			gabarit
		});
		expect(cree.confirme).toBe(false);
		expect(comptes.brouillon(cree.id)).toEqual({ profil: 'RSSI', prenom: 'Adrien', gabarit });
		comptes.confirmer(cree.id);
		expect(comptes.parId(cree.id)?.confirme).toBe(true);
		expect(comptes.brouillon(cree.id)).toEqual({ profil: '', prenom: '', gabarit: null });
	});

	it('confirmer ne vaut qu’une fois', async () => {
		const { comptes } = monter();
		const cree = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		expect(comptes.confirmer(cree.id)).toBe(true);
		expect(comptes.confirmer(cree.id)).toBe(false);
		expect(comptes.parId(cree.id)?.confirme).toBe(true);
	});

	it('note la première connexion une seule fois', async () => {
		const { creerConfirme, comptes } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		expect(comptes.noterPremiereConnexion(moi.id)).toBe(true);
		expect(comptes.noterPremiereConnexion(moi.id)).toBe(false);
	});

	it('les comptes confirmés avant la migration ne sont pas une première connexion', async () => {
		const base = new DatabaseSync(':memory:');
		migrer(base, 2);
		const inserer = base.prepare(
			'INSERT INTO comptes (email, username, hash, cree_le, confirme_le) VALUES (?, ?, ?, ?, ?)'
		);
		const ancien = Number(inserer.run('ancien@example.com', 'ancien', 'x', '2026-01-01', '2026-01-01').lastInsertRowid);
		const attente = Number(inserer.run('attente@example.com', 'attente', 'x', '2026-11-20', null).lastInsertRowid);
		migrer(base);

		const comptes = new Comptes(base, EMAIL_ADMIN, new FauxHacheur());
		expect(comptes.noterPremiereConnexion(ancien)).toBe(false);
		// Un compte encore en attente au déploiement aura bien sa première connexion.
		comptes.confirmer(attente);
		expect(comptes.noterPremiereConnexion(attente)).toBe(true);
	});

	it("signale l'email ou le username déjà pris, même par un compte en attente", async () => {
		const { comptes } = monter();
		await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		expect(comptes.conflit('MOI@example.com', 'autre')?.champ).toBe('email');
		expect(comptes.conflit('autre@example.com', 'moi')?.champ).toBe('username');
		expect(comptes.conflit('autre@example.com', 'autre')).toBeNull();
		await expect(comptes.creer('autre@example.com', 'moi', 'une phrase de passe')).rejects.toBeInstanceOf(
			CompteExistant
		);
	});

	it("ne fait administrateur l'adresse de ADMIN_EMAIL qu'une fois le compte confirmé", async () => {
		const { comptes } = monter();
		const admin = await comptes.creer(EMAIL_ADMIN.toUpperCase(), 'chef', 'une phrase de passe');
		expect(admin.admin).toBe(false);
		expect(comptes.lister().find((c) => c.username === 'chef')).toMatchObject({ admin: false, confirme: false });

		comptes.confirmer(admin.id);
		expect(comptes.parId(admin.id)?.admin).toBe(true);
		expect(comptes.lister().find((c) => c.username === 'chef')).toMatchObject({ admin: true, confirme: true });
	});

	it('ne donne le rôle admin en base qu’à un compte confirmé', async () => {
		const { base, comptes } = monter();
		const membre = await comptes.creer('membre@example.com', 'membre', 'une phrase de passe');
		base.prepare("UPDATE comptes SET role = 'admin' WHERE id = ?").run(membre.id);
		expect(comptes.parId(membre.id)?.admin).toBe(false);
		comptes.confirmer(membre.id);
		expect(comptes.parId(membre.id)?.admin).toBe(true);
	});

	it('ne fait personne administrateur quand ADMIN_EMAIL est vide', async () => {
		const comptes = new Comptes(ouvrirBase(':memory:'), '', new FauxHacheur());
		const u = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		comptes.confirmer(u.id);
		expect(comptes.parId(u.id)?.admin).toBe(false);
	});

	it('contrôle la consultation : le propriétaire ou l’administrateur', async () => {
		const { creerConfirme } = monter();
		const admin = await creerConfirme(EMAIL_ADMIN, 'chef');
		const moi = await creerConfirme('moi@example.com', 'moi');
		expect(moi.peutConsulter('moi')).toBe(true);
		expect(moi.peutConsulter('chef')).toBe(false);
		expect(admin.peutConsulter('moi')).toBe(true);
	});

	it('purge les comptes jamais confirmés au bout de sept jours, et eux seuls', async () => {
		const h = { t: 1_800_000_000_000 };
		const { comptes, sessions } = monter(() => h.t);
		const abandonne = await comptes.creer('abandon@example.com', 'abandon', 'une phrase de passe');
		const confirme = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		comptes.confirmer(confirme.id);
		sessions.ouvrir(confirme.id);

		h.t += DELAI_CONFIRMATION_COMPTE_MS - 1;
		expect(comptes.purgerNonConfirmes()).toBe(0);
		h.t += 2;
		expect(comptes.purgerNonConfirmes()).toBe(1);
		expect(comptes.parId(abandonne.id)).toBeNull();
		expect(comptes.parId(confirme.id)).not.toBeNull();
		expect(comptes.conflit('abandon@example.com', 'abandon')).toBeNull();
	});

	it('monte le schéma jusqu’à la version des demandes de magic-link', () => {
		const base = ouvrirBase(':memory:');
		expect(base.prepare('PRAGMA user_version').get()).toEqual({ user_version: 8 });
	});

	it('compte une consultation une fois par compte et par jour', () => {
		const h = { t: Date.parse('2026-11-23T10:00:00Z') };
		const { base, comptes, sessions } = monter(() => h.t);
		const moi = { id: 1 } as never;
		const insert = base.prepare('INSERT INTO comptes (email, username, hash, role, cree_le, confirme_le) VALUES (?, ?, ?, ?, ?, ?)');
		insert.run('moi@example.test', 'moi', 'faux', 'membre', new Date(h.t).toISOString(), new Date(h.t).toISOString());
		const id = 1;
		base.prepare('INSERT OR IGNORE INTO consultations (compte_id, jour) VALUES (?, ?)').run(id, '2026-11-23');
		base.prepare('INSERT OR IGNORE INTO consultations (compte_id, jour) VALUES (?, ?)').run(id, '2026-11-23');
		expect(base.prepare('SELECT COUNT(*) AS nombre FROM consultations WHERE compte_id = ?').get(id)).toEqual({ nombre: 1 });
		expect(comptes.consultationsSeptJours(id)).toBe(1);
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
