import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LIEN_DESABONNEMENT_INVALIDE } from '#lib/server/desabonnement.js';
import { monter } from '#lib/server/outils-test.js';
import Page from './+page.svelte';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load, actions } = await import('./+page.server.js');

const JETON = 'v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71.empreinte.signature';

type Env = ReturnType<typeof monter>;

/** L'évènement que SvelteKit passerait : sans personne connectée, et rien d'autre que le
 * jeton de l'URL. Le corps du POST en un clic n'est jamais lu. */
function evenement(jeton = JETON) {
	return {
		params: { jeton },
		locals: { utilisateur: null },
		request: new Request(`https://site.test/desabonnement/${jeton}`, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded' },
			body: 'List-Unsubscribe=One-Click'
		})
	} as never;
}

async function avecProfil(): Promise<Env> {
	const env = monter();
	await env.api.creerProfil('bea', {
		profil: 'Veille',
		stack: [],
		email: ['b@example.com', 'c@example.com'],
		prenom: '',
		securite: 'exploitant'
	});
	env.fausseApi.ajouterDesabonnement(JETON, 'bea');
	etat.env = env;
	return env;
}

function rendre(data: Record<string, unknown>, form: unknown = null): string {
	const props = { data, form };
	return render(Page, { props } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

describe('/desabonnement/[jeton]', () => {
	let env: Env;
	beforeEach(async () => {
		env = await avecProfil();
	});

	it("l'affichage ne désabonne pas", async () => {
		const data = await load(evenement());

		expect(data).toEqual({ demande: { username: 'bea', destinataires: 2 }, invalide: null });
		expect((await env.api.lireProfil('bea')).email).toEqual(['b@example.com', 'c@example.com']);
		const html = rendre(data as Record<string, unknown>);
		expect(html).toContain('ne sera plus envoyé à ses 2 destinataires');
		expect(html).toContain('<form method="POST"');
	});

	it('désabonne sans personne connectée, une seule fois', async () => {
		const premier = await actions.default(evenement());
		expect(premier).toEqual({ desabonne: 'bea' });
		expect((await env.api.lireProfil('bea')).email).toEqual([]);
		expect(rendre({ demande: null, invalide: null }, premier)).toContain('href="/profil"');

		const second = (await actions.default(evenement())) as { status: number; data: { message: string } };
		expect(second.status).toBe(400);
		expect(second.data.message).toBe(LIEN_DESABONNEMENT_INVALIDE);
		expect(second.data.message).toContain('invalide ou déjà utilisé');
		expect(await load(evenement())).toEqual({ demande: null, invalide: LIEN_DESABONNEMENT_INVALIDE });
	});

	it('montre le refus d’un lien inconnu, sans formulaire', async () => {
		const data = await load(evenement('v1.inconnu.x.y'));

		expect(data).toEqual({ demande: null, invalide: LIEN_DESABONNEMENT_INVALIDE });
		expect(rendre(data as Record<string, unknown>)).not.toContain('<form');
	});
});
