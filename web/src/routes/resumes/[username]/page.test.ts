import { isRedirect } from '@sveltejs/kit';
import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Utilisateur } from '#lib/server/comptes.js';
import { EMAIL_ADMIN, monter } from '#lib/server/outils-test.js';
import Page from './+page.svelte';

/* Le contexte réel lit l'environnement et ouvre la base : le load reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load } = await import('./+page.server.js');

const PASSAGE = { heure: '04:00', fuseau: 'Europe/Paris', prochain: '2026-11-23T04:00:00+01:00' };

function rendre(data: Record<string, unknown>): string {
	const props = {
		data: { username: 'moi', proprietaire: true, journees: [], passage: null, erreur: null, ...data },
		params: { username: String(data.username ?? 'moi') }
	};
	// La page n'attend que `data` ; le reste des props de SvelteKit n'y sert pas.
	return render(Page, { props } as unknown as Parameters<typeof render<typeof Page>>[1]).body;
}

describe('page des résumés, état vide', () => {
	it("annonce le passage, et non une heure d'arrivée, à son propriétaire", () => {
		const html = rendre({ passage: PASSAGE });
		expect(html).toContain('Votre premier résumé arrivera après le passage du lundi 23 novembre à 04:00.');
	});

	it("parle de l'autre personne à un administrateur", () => {
		const html = rendre({ username: 'bea', proprietaire: false, passage: PASSAGE });
		expect(html).toContain('Le premier résumé de bea arrivera après le passage du lundi 23 novembre à 04:00.');
		expect(html).not.toContain('Votre premier');
	});

	it('garde la phrase sans heure quand le passage est inconnu', () => {
		expect(rendre({})).toContain('Le premier arrivera après le prochain passage quotidien.');
	});

	it('pointe chaque journée vers sa page de lecture', () => {
		const html = rendre({ journees: [{ date: '2026-11-21', audios: [] }] });
		expect(html).toContain('href="/resumes/moi/2026-11-21"');
	});

	it('affiche durée, catégories et articles pour une carte', () => {
		const html = rendre({
			journees: [{ date: '2026-11-21', audios: [{ nom: 'jour.mp3', taille: 2048 }] }],
			indicateursJournees: {
				'2026-11-21': { ecoute: '8 min', categories: 4, articles: 5 }
			}
		});
		expect(html).toContain('8 MIN');
		expect(html).toContain('4 catégories');
		expect(html).toContain('5 articles');
	});
});

describe('page des résumés, journées lues', () => {
	it('distingue la journée lue, et elle seule', () => {
		const html = rendre({
			journees: [
				{ date: '2026-11-22', audios: [] },
				{ date: '2026-11-21', audios: [{ nom: 'jour.mp3', taille: 2048 }] }
			],
			lues: ['2026-11-21']
		});
		const cartes = html.split('<li class="carte journee').slice(1);
		expect(cartes).toHaveLength(2);
		expect(cartes[0]).not.toMatch(/^[^>]*\blue\b/);
		expect(cartes[0]).not.toContain('pastille-lue');
		expect(cartes[1]).toMatch(/^[^>]*\blue\b/);
		expect(cartes[1]).toMatch(/<span class="pastille-lue[^"]*">Lue<\/span>/);
	});

	it('ne précharge jamais la journée : toucher le lien en faisant défiler ne la marque pas', () => {
		const html = rendre({
			journees: [
				{ date: '2026-11-22', audios: [] },
				{ date: '2026-11-21', audios: [{ nom: 'jour.mp3', taille: 2048 }] }
			]
		});
		const liens = html.match(/<a [^>]*>Lire le résumé<\/a>/g) ?? [];
		expect(liens).toHaveLength(2);
		for (const lien of liens) expect(lien).toContain('data-sveltekit-preload-data="off"');
	});
});

describe('/resumes/[username] — le chargement des journées lues', () => {
	let env: ReturnType<typeof monter>;
	let bea: Utilisateur;
	let admin: Utilisateur;

	function evenement(utilisateur: Utilisateur | null, username = 'bea') {
		return {
			params: { username },
			url: new URL(`https://site.test/resumes/${username}`),
			locals: { utilisateur }
		} as never;
	}

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterContenu('bea', '2026-11-21', {});
		env.fausseApi.ajouterContenu('bea', '2026-11-22', {});
		bea = await env.creerConfirme('bea@example.com', 'bea');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		env.journeesLues.marquer(bea, 'bea', '2026-11-21', 'pages');
		etat.env = env;
	});

	it('rend au propriétaire les journées qu’il a lues', async () => {
		expect(await load(evenement(bea))).toMatchObject({ lues: ['2026-11-21'] });
	});

	it('ne rend rien hors session : la page renvoie à la connexion', async () => {
		let lancee: unknown;
		try {
			await load(evenement(null));
		} catch (erreur) {
			lancee = erreur;
		}
		expect(isRedirect(lancee)).toBe(true);
		expect((lancee as { location: string }).location).toMatch(/^\/connexion/);
	});

	it("ne montre pas à un admin les lectures de l'autre", async () => {
		expect(await load(evenement(admin))).toMatchObject({ lues: [] });
	});
});
