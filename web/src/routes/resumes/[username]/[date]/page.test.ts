import { isHttpError, isRedirect } from '@sveltejs/kit';
import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Utilisateur } from '#lib/server/comptes.js';
import { ConsultationResumes } from '#lib/server/consultation.js';
import { EMAIL_ADMIN, monter } from '#lib/server/outils-test.js';
import { CLE_LECTEUR, LecteurAudio } from '#lib/lecteur.svelte.js';
import Page from './+page.svelte';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load, actions } = await import('./+page.server.js');

const JOUR = '2026-11-22';

type Env = ReturnType<typeof monter>;

function evenement(utilisateur: Utilisateur | null, corps: Record<string, string> = {}, username = 'bea') {
	const url = new URL(`https://site.test/resumes/${username}/${JOUR}`);
	return {
		params: { username, date: JOUR },
		url,
		locals: { utilisateur },
		request: new Request(url, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams(corps).toString()
		})
	} as never;
}

function rendre(data: unknown, form: unknown = null): string {
	const props = { data, form };
	const context = new Map([[CLE_LECTEUR, new LecteurAudio()]]);
	return render(Page, { props, context } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

async function leve(promesse: unknown): Promise<unknown> {
	try {
		await promesse;
	} catch (lancee) {
		return lancee;
	}
	throw new Error("rien n'a été levé");
}

describe('/resumes/[username]/[date] — le vote', () => {
	let env: Env;
	let bea: Utilisateur;
	let admin: Utilisateur;

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterContenu('bea', JOUR, {});
		bea = await env.creerConfirme('bea@example.com', 'bea');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		etat.env = { ...env, consultation: new ConsultationResumes(env.api) };
	});

	it('montre le formulaire au propriétaire, pré-rempli du vote déjà donné', async () => {
		await env.api.voter('bea', JOUR, 'pas_utile', 'Laissé depuis la lettre.');

		const data = await load(evenement(bea));

		expect(data).toMatchObject({ proprietaire: true, retour: { avis: 'pas_utile', commentaire: 'Laissé depuis la lettre.' } });
		const html = rendre(data);
		expect(html).toContain('Votre avis sur cette journée');
		expect(html).toContain('Laissé depuis la lettre.</textarea>');
		expect(html).toMatch(/<input[^>]*value="pas_utile"[^>]*checked/);
	});

	it("ne montre pas le formulaire à un admin qui consulte la journée d'un autre, ni ne lit son vote", async () => {
		const avant = env.fausseApi.requetes.length;

		const data = await load(evenement(admin));

		expect(data).toMatchObject({ proprietaire: false, retour: null });
		expect(
			env.fausseApi.requetes.slice(avant).some((requete) => requete.url.endsWith('/retour'))
		).toBe(false);
		expect(rendre(data)).not.toContain('Envoyer mon avis');
	});

	it('enregistre le vote du propriétaire, et le second remplace le premier', async () => {
		const premier = await actions.default(evenement(bea, { avis: 'utile', commentaire: 'Bien.' }));
		expect(premier).toMatchObject({ vote: { avis: 'utile', commentaire: 'Bien.' } });

		await actions.default(evenement(bea, { avis: 'pas_utile', commentaire: '' }));

		expect(env.fausseApi.retours.size).toBe(1);
		expect(await env.api.lireRetour('bea', JOUR)).toMatchObject({ avis: 'pas_utile', commentaire: '' });
	});

	it("refuse le vote d'un admin sur la journée d'un autre, et celui de qui n'est pas connecté", async () => {
		const refus = await leve(actions.default(evenement(admin, { avis: 'utile' })));
		expect(isHttpError(refus, 404)).toBe(true);

		const anonyme = await leve(actions.default(evenement(null, { avis: 'utile' })));
		expect(isRedirect(anonyme)).toBe(true);

		expect(env.fausseApi.retours.size).toBe(0);
	});

	it("refuse le vote sur une journée qui n'existe pas", async () => {
		const autreJour = {
			...(evenement(bea, { avis: 'utile' }) as Record<string, unknown>),
			params: { username: 'bea', date: '2026-11-21' }
		} as never;

		expect(isHttpError(await leve(actions.default(autreJour)), 404)).toBe(true);
		expect(env.fausseApi.retours.size).toBe(0);
	});
});
