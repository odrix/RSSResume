import { isHttpError, isRedirect } from '@sveltejs/kit';
import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GABARITS_DEMO, mp3Silencieux } from '../../../mock/faux-api.js';

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

function evenement(utilisateur: Utilisateur | null, recherche = '') {
	return { locals: { utilisateur }, url: new URL(`https://site.test/admin${recherche}`) } as never;
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

		const data = (await load(evenement(admin, '?onglet=retours'))) as { retours: { commentaire: string }[]; erreurRetours: null };

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

		const html = rendre(await load(evenement(admin, '?onglet=retours')));

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
		etat.env = { ...env, api, retours: new Retours(api, env.comptes) };

		const data = (await load(evenement(admin))) as { erreurRetours: string; lignes: unknown[] };

		expect(data.erreurRetours).toBe('Erreur interne.');
		expect(data.lignes.length).toBeGreaterThan(0);
	});
});

describe('/admin, les onglets', () => {
	let env: Env;

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		etat.env = env;
	});

	it('affiche la liste des profils par défaut et valide le paramètre onglet', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');

		const defaut = (await load(evenement(admin))) as { onglet: string };
		expect(defaut.onglet).toBe('profils');

		const stats = (await load(evenement(admin, '?onglet=stats'))) as { onglet: string };
		expect(stats.onglet).toBe('stats');

		const retours = (await load(evenement(admin, '?onglet=retours'))) as { onglet: string };
		expect(retours.onglet).toBe('retours');

		const inconnu = (await load(evenement(admin, '?onglet=bidon'))) as { onglet: string };
		expect(inconnu.onglet).toBe('profils');

		const html = rendre(await load(evenement(admin, '?onglet=stats')));
		expect(html).toContain('href="/admin?onglet=retours"');
		expect(html).toContain('Profils choisis');
		expect(html).toContain('Types de sécurité');
		expect(html).toContain('<svg');
	});
});

describe('/admin, les lignes et les stats', () => {
	let env: Env;

	const AUIJOURD_HUI = new Date().toISOString().slice(0, 10);
	const ilYa = (jours: number) => new Date(Date.now() - jours * 86_400_000).toISOString().slice(0, 10);

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', {
			profil: GABARITS_DEMO[0].profil,
			stack: [],
			email: ['bea@example.com'],
			prenom: 'Béa',
			securite: 'decideur',
			categories: ['Cybersécurité', 'Tech generaliste']
		});
		await env.api.creerProfil('cle', {
			profil: 'Un texte écrit à la main.',
			stack: [],
			email: [],
			prenom: '',
			securite: 'curieux'
		});
		etat.env = env;
	});

	it('compte les journées sur 7 et 30 jours et nomme le profil choisi', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		for (const date of [AUIJOURD_HUI, ilYa(3), ilYa(10), ilYa(40)]) {
			env.fausseApi.ajouterAudio('bea', date, 'journee.mp3', mp3Silencieux(2));
		}

		const data = (await load(evenement(admin))) as {
			lignes: { username: string; journees7j: number; journees30j: number; profilChoisi: string; securite: string; categoriesLibelles: string[] }[];
		};
		const bea = data.lignes.find((ligne) => ligne.username === 'bea')!;
		expect(bea.journees7j).toBe(2);
		expect(bea.journees30j).toBe(3);
		expect(bea.profilChoisi).toBe('CTO, direction technique');
		expect(bea.securite).toBe('decideur');
		expect(bea.categoriesLibelles).toEqual(['Cybersécurité', 'Tech generaliste']);

		const cle = data.lignes.find((ligne) => ligne.username === 'cle')!;
		expect(cle.profilChoisi).toBe('Personnalisé');
		expect(cle.journees7j).toBe(0);
	});

	it('met 0 quand le coût est inconnu et calcule le coût par résumé', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		env.fausseApi.ajouterAudio('bea', AUIJOURD_HUI, 'journee.mp3', mp3Silencieux(2));
		env.fausseApi.ajouterAudio('bea', ilYa(1), 'journee.mp3', mp3Silencieux(2));
		env.fausseApi.ajouterCouts('bea', {
			couts_7j: { devise: 'EUR', total: 0.9, tarification_complete: true, modeles_sans_tarif: [] },
			couts_30j: { devise: 'EUR', total: null, tarification_complete: false, modeles_sans_tarif: ['modele-x'] }
		});

		const data = (await load(evenement(admin))) as {
			lignes: { username: string; couts7j: { total: number }; couts30j: { total: null; tarification_complete: boolean } }[];
		};
		const bea = data.lignes.find((ligne) => ligne.username === 'bea')!;
		expect(bea.couts7j.total).toBe(0.9);
		expect(bea.couts30j.tarification_complete).toBe(false);

		const html = rendre(data);
		// Le coût 30 j inconnu s'affiche 0, avec le modèle sans tarif signalé à côté.
		expect(html).toContain('0.000000 EUR');
		expect(html).toContain('tarif partiel : modele-x');
		// 0,9 EUR sur 2 journées : 0,45 par résumé.
		expect(html).toContain('0.450000 EUR');
		expect(html).not.toContain('? (');
	});

	it('montre les écoutes et les retours des 7 derniers jours, admin seulement', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		const bea = await env.creerConfirme('bea@example.com', 'bea');
		const cle = await env.creerConfirme('cle@example.com', 'cle');
		await env.api.creerProfil('sanscompte', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });

		// Deux écoutes pour bea (deux journées), une pour cle, une vieille hors fenêtre.
		env.comptes.noterEcoute(bea.id, ilYa(1));
		env.comptes.noterEcoute(bea.id, ilYa(2));
		env.comptes.noterEcoute(bea.id, ilYa(2)); // même journée, même jour : une seule
		env.comptes.noterEcoute(cle.id, AUIJOURD_HUI);
		env.base
			.prepare('INSERT OR IGNORE INTO ecoutes (compte_id, jour, journee) VALUES (?, ?, ?)')
			.run(bea.id, ilYa(10), ilYa(10));

		// Des retours venus du lien de la lettre, pour bea et pour un profil sans compte.
		env.comptes.noterRetour('bea', ilYa(1), 'utile');
		env.comptes.noterRetour('bea', ilYa(3), 'pas_utile');
		env.comptes.noterRetour('bea', ilYa(3), 'utile'); // remplacé : toujours une journée
		env.comptes.noterRetour('sanscompte', AUIJOURD_HUI, 'pas_utile');
		env.base.prepare('INSERT INTO retours (username, journee, avis) VALUES (?, ?, ?)').run('bea', ilYa(10), 'utile');

		const membre = await env.creerConfirme('membre@example.com', 'membre');
		expect(isHttpError(await leve(load(evenement(membre))))).toBe(true);

		const data = (await load(evenement(admin))) as {
			lignes: { username: string; ecoutes7j: number; retours7j: number }[];
		};
		const parNom = (username: string) => data.lignes.find((ligne) => ligne.username === username)!;
		expect(parNom('bea').ecoutes7j).toBe(2);
		expect(parNom('bea').retours7j).toBe(2);
		expect(parNom('cle').ecoutes7j).toBe(1);
		expect(parNom('cle').retours7j).toBe(0);
		expect(parNom('sanscompte').retours7j).toBe(1);
		expect(parNom('sanscompte').ecoutes7j).toBe(0);

		const html = rendre(data);
		expect(html).toContain('Écoutes 7 j');
		expect(html).toContain('Retours 7 j');
	});

	it('calcule les répartitions pour les stats', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');

		const data = (await load(evenement(admin, '?onglet=stats'))) as {
			repartitionProfils: { libelle: string; nombre: number }[];
			repartitionSecurite: { libelle: string; nombre: number }[];
			parCategorie: { libelle: string; nombre: number }[];
		};

		expect(data.repartitionProfils).toEqual([
			{ libelle: 'CTO, direction technique', nombre: 1 },
			{ libelle: 'Personnalisé', nombre: 1 }
		]);
		expect(data.repartitionSecurite).toEqual([
			{ libelle: 'curieux', nombre: 1 },
			{ libelle: 'decideur', nombre: 1 }
		]);
		expect(data.parCategorie).toEqual([
			{ libelle: 'Cybersécurité', nombre: 1 },
			{ libelle: 'Tech generaliste', nombre: 1 },
			{ libelle: 'Toutes les catégories', nombre: 1 }
		]);

		const html = rendre(data);
		expect(html).toContain('Catégories suivies');
		expect(html).toContain('Toutes les catégories');
		expect(html).toContain('Décideur');
	});
});
