import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LONGUEUR_MAX_COMMENTAIRE } from '#lib/retour.js';
import { monter } from '#lib/server/outils-test.js';
import { LIEN_RETOUR_INVALIDE } from '#lib/server/retours.js';
import Page from './+page.svelte';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load, actions } = await import('./+page.server.js');

const JETON = 'v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71.2026-11-22.signature';

type Env = ReturnType<typeof monter>;

/** L'évènement que SvelteKit passerait : personne de connecté, le jeton de l'URL, l'avis du
 * lien cliqué en paramètre, et le corps du formulaire pour l'action. */
function evenement(options: { jeton?: string; avis?: string; corps?: Record<string, string> } = {}) {
	const jeton = options.jeton ?? JETON;
	const url = new URL(`https://site.test/retour/${jeton}`);
	if (options.avis) url.searchParams.set('avis', options.avis);
	return {
		params: { jeton },
		url,
		locals: { utilisateur: null },
		request: new Request(url, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams(options.corps ?? {}).toString()
		})
	} as never;
}

function rendre(data: Record<string, unknown>, form: unknown = null): string {
	const props = { data, form };
	return render(Page, { props } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

/** La case cochée du rendu, s'il y en a une. */
function cochee(html: string): string | null {
	const balise = (html.match(/<input[^>]*name="avis"[^>]*>/g) ?? []).find((b) => /\schecked(=""|\s|>|\/)/.test(b));
	return balise ? /value="([^"]*)"/.exec(balise)![1] : null;
}

describe('/retour/[jeton]', () => {
	let env: Env;
	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterLienRetour(JETON, 'bea', '2026-11-22');
		etat.env = env;
	});

	it("l'affichage ne vote pas : il pré-coche l'avis du lien et attend l'envoi", async () => {
		const data = await load(evenement({ avis: 'pas_utile' }));

		expect(data).toEqual({
			lecture: { username: 'bea', jour: '2026-11-22', retour: null },
			avis: 'pas_utile',
			invalide: null
		});
		// Aucun vote n'est parti : seule la lecture a été demandée à l'API.
		expect(env.fausseApi.requetes.map((r) => `${r.method} ${new URL(r.url).pathname}`)).toEqual([
			'POST /api/v1/profils',
			'POST /api/v1/retours/lecture'
		]);
		expect(env.fausseApi.retours.size).toBe(0);
		const html = rendre(data as Record<string, unknown>);
		expect(cochee(html)).toBe('pas_utile');
		expect(html).toContain('<form method="POST"');
		expect(html).toContain(`maxlength="${LONGUEUR_MAX_COMMENTAIRE}"`);
		expect(html).toContain("Votre avis n'est compté qu'une fois envoyé");
		expect(html).toContain('Envoyer mon avis');
	});

	it('vote sans personne connectée, et un second envoi remplace le premier', async () => {
		const premier = await actions.default(evenement({ corps: { avis: 'utile', commentaire: 'Bien.' } }));
		expect(premier).toMatchObject({ vote: { username: 'bea', jour: '2026-11-22', retour: { avis: 'utile' } } });
		expect(rendre({ lecture: null, avis: null, invalide: null }, premier)).toContain('« Utile »');

		await actions.default(evenement({ corps: { avis: 'pas_utile', commentaire: 'Finalement non.' } }));

		expect(env.fausseApi.retours.size).toBe(1);
		const relu = await load(evenement());
		expect(relu).toMatchObject({ avis: 'pas_utile', lecture: { retour: { commentaire: 'Finalement non.' } } });
		// Le commentaire déjà laissé est pré-rempli : renvoyer le formulaire ne l'efface pas.
		const html = rendre(relu as Record<string, unknown>);
		expect(html).toContain('Finalement non.</textarea>');
		expect(html).toContain('il remplacera le précédent');
	});

	it('garde le commentaire saisi quand l’envoi est refusé', async () => {
		const trop = 'x'.repeat(LONGUEUR_MAX_COMMENTAIRE + 1);
		const refus = (await actions.default(evenement({ corps: { avis: 'utile', commentaire: trop } }))) as {
			status: number;
			data: { message: string; commentaire: string };
		};

		expect(refus.status).toBe(400);
		expect(refus.data.commentaire).toBe(trop);
		expect(env.fausseApi.retours.size).toBe(0);

		const sansAvis = (await actions.default(evenement({ corps: { commentaire: 'Texte.' } }))) as {
			status: number;
			data: { commentaire: string };
		};
		expect(sansAvis.status).toBe(400);
		expect(sansAvis.data.commentaire).toBe('Texte.');
	});

	it('montre le refus d’un lien inconnu, sans formulaire, et refuse son vote', async () => {
		const data = await load(evenement({ jeton: 'v1.inconnu.2026-11-22.x' }));

		expect(data).toEqual({ lecture: null, avis: null, invalide: LIEN_RETOUR_INVALIDE });
		expect(rendre(data as Record<string, unknown>)).not.toContain('<form');

		const refus = (await actions.default(
			evenement({ jeton: 'v1.inconnu.2026-11-22.x', corps: { avis: 'utile' } })
		)) as { status: number; data: { message: string } };
		expect(refus.status).toBe(400);
		expect(refus.data.message).toBe(LIEN_RETOUR_INVALIDE);
		expect(env.fausseApi.retours.size).toBe(0);
	});

	it('refuse le lien d’un profil supprimé depuis', async () => {
		await env.api.supprimerProfil('bea');

		expect(await load(evenement())).toEqual({ lecture: null, avis: null, invalide: LIEN_RETOUR_INVALIDE });
	});
});
