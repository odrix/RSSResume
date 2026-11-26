import { isHttpError, isRedirect } from '@sveltejs/kit';
import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientApiResume } from '#lib/server/api-resume.js';
import type { Utilisateur } from '#lib/server/comptes.js';
import { EMAIL_ADMIN, JETON, monter } from '#lib/server/outils-test.js';
import { Retours } from '#lib/server/retours.js';
import Page from './+page.svelte';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load } = await import('./+page.server.js');

type Env = ReturnType<typeof monter>;

function evenement(utilisateur: Utilisateur | null) {
	return { locals: { utilisateur }, url: new URL('https://site.test/admin') } as never;
}

function rendre(data: unknown): string {
	return render(Page, { props: { data } } as unknown as Parameters<typeof render<typeof Page>>[1]).body;
}

async function leve(promesse: unknown): Promise<unknown> {
	try {
		await promesse;
	} catch (lancee) {
		return lancee;
	}
	throw new Error("rien n'a été levé");
}

/** Les demandes de la liste des retours que la fausse API a reçues. */
function listesDemandees(env: Env): number {
	return env.fausseApi.requetes.filter((r) => r.method === 'GET' && new URL(r.url).pathname === '/api/v1/retours')
		.length;
}

describe('/admin, les retours', () => {
	let env: Env;

	beforeEach(async () => {
		env = monter();
		for (const username of ['bea', 'cle']) {
			await env.api.creerProfil(username, { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		}
		etat.env = env;
	});

	it("n'est pas montrée à un membre, ni demandée à l'API pour lui", async () => {
		const membre = await env.creerConfirme('bea@example.com', 'bea');

		expect(isHttpError(await leve(load(evenement(membre))), 404)).toBe(true);
		expect(isRedirect(await leve(load(evenement(null))))).toBe(true);
		expect(listesDemandees(env)).toBe(0);
	});

	it("liste les retours à l'admin, du plus récent au plus ancien", async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		await env.api.voter('bea', '2026-11-20', 'utile', 'Premier.');
		await env.api.voter('cle', '2026-11-21', 'pas_utile', 'Deuxième.');
		await env.api.voter('bea', '2026-11-22', 'utile', 'Troisième.');

		const data = (await load(evenement(admin))) as { retours: { commentaire: string }[]; erreurRetours: null };

		expect(listesDemandees(env)).toBe(1);
		expect(data.erreurRetours).toBeNull();
		expect(data.retours.map((retour) => retour.commentaire)).toEqual(['Troisième.', 'Deuxième.', 'Premier.']);
		const html = rendre(data);
		expect(html).toContain('href="/resumes/cle/2026-11-21"');
		expect(html).toContain('Pas utile');
	});

	it('rend le commentaire échappé, jamais comme du balisage', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		await env.api.voter('bea', '2026-11-22', 'pas_utile', '<script>alert(1)</script>\n<b>gras</b>');

		const html = rendre(await load(evenement(admin)));

		expect(html).toMatch(/&lt;script(&gt;|>)alert\(1\)&lt;\/script(&gt;|>)/);
		expect(html).not.toContain('<script>alert');
		expect(html).not.toContain('<b>gras</b>');
		expect(html).toContain('class="commentaire');
	});

	it("garde les profils quand la liste des retours est indisponible", async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		const api = new ClientApiResume({
			baseUrl: 'http://api.test/',
			jeton: JETON,
			fetch: async (entree, init) => {
				const requete = new Request(entree, init);
				if (new URL(requete.url).pathname === '/api/v1/retours') {
					return new Response(JSON.stringify({ erreur: 'Erreur interne.' }), { status: 500 });
				}
				return env.fausseApi.traiter(requete);
			}
		});
		etat.env = { ...env, api, retours: new Retours(api) };

		const data = (await load(evenement(admin))) as { erreurRetours: string; lignes: unknown[] };

		expect(data.erreurRetours).toBe('Erreur interne.');
		expect(data.lignes.length).toBeGreaterThan(0);
	});
});
