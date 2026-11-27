import { isHttpError, isRedirect } from '@sveltejs/kit';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Utilisateur } from '#lib/server/comptes.js';

import { EMAIL_ADMIN, monter } from '#lib/server/outils-test.js';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));

vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { GET } = await import('./+server.js');

type Env = ReturnType<typeof monter>;

function evenement(utilisateur: Utilisateur | null, username = 'bea', decalage = '7') {
	return {
		params: { username },
		url: new URL(`https://site.test/resumes/${username}/lots?decalage=${decalage}`),
		locals: { utilisateur }
	} as never;
}

async function leve(promesse: unknown): Promise<unknown> {
	try {
		await promesse;
	} catch (lancee) {
		return lancee;
	}
	throw new Error("rien n'a été levé");
}

describe('GET /resumes/[username]/lots', () => {
	let env: Env;
	let bea: Utilisateur;
	let admin: Utilisateur;
	let autre: Utilisateur;

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		for (let jour = 1; jour <= 25; jour++) {
			env.fausseApi.ajouterContenu('bea', `2026-10-${String(jour).padStart(2, '0')}`, {});
		}
		bea = await env.creerConfirme('bea@example.com', 'bea');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		autre = await env.creerConfirme('autre@example.com', 'autre');
		etat.env = env;
	});

	it('rend le lot suivant au-delà de 7, dans l’ordre décroissant, avec total et aSuite', async () => {
		const reponse = await GET(evenement(bea, 'bea', '7'));
		expect(reponse.status).toBe(200);
		const lot = await reponse.json();
		expect(lot.total).toBe(25);
		expect(lot.journees).toHaveLength(7);
		expect(lot.aSuite).toBe(true);
		expect(lot.journees[0].date).toBe('2026-10-18');
		expect(lot.journees.at(-1).date).toBe('2026-10-12');
		// Les indicateurs suivent le lot, pour des cartes identiques à celles du 1er lot.
		expect(Object.keys(lot.indicateursJournees)).toHaveLength(7);
	});

	it('rend aSuite false au dernier lot', async () => {
		const reponse = await GET(evenement(bea, 'bea', '21'));
		const lot = await reponse.json();
		expect(lot.total).toBe(25);
		expect(lot.journees).toHaveLength(4);
		expect(lot.journees.at(-1).date).toBe('2026-10-01');
		expect(lot.aSuite).toBe(false);
	});

	it("un administrateur peut charger les lots du profil d'un autre", async () => {
		const reponse = await GET(evenement(admin, 'bea', '7'));
		expect(reponse.status).toBe(200);
		expect((await reponse.json()).journees).toHaveLength(7);
	});

	it('rend 404 à qui n’a pas le droit de consulter, sans dire si le profil existe', async () => {
		expect(isHttpError(await leve(GET(evenement(autre, 'bea', '7'))), 404)).toBe(true);
		expect(isHttpError(await leve(GET(evenement(autre, 'inconnu', '0'))), 404)).toBe(true);
	});

	it("rend 404 quand l'API ne connaît pas le profil consulté par un admin", async () => {
		expect(isHttpError(await leve(GET(evenement(admin, 'inconnu', '0'))), 404)).toBe(true);
	});

	it('renvoie vers la connexion sans session', async () => {
		const lancee = await leve(GET(evenement(null)));
		expect(isRedirect(lancee)).toBe(true);
		expect((lancee as { location: string }).location).toMatch(/^\/connexion/);
	});

	it('rend 400 pour un decalage qui n’est pas un entier positif', async () => {
		for (const decalage of ['abc', '-1', '1.5']) {
			expect(isHttpError(await leve(GET(evenement(bea, 'bea', decalage))), 400)).toBe(true);
		}
	});
});
