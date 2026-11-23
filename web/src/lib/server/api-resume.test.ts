import { describe, expect, it } from 'vitest';
import { GABARITS_DEMO, mp3Silencieux } from '../../../mock/faux-api.js';
import { ClientApiResume, ErreurApi } from './api-resume.js';
import { JETON, monter } from './outils-test.js';

const SAISIE = {
	profil: 'CTO',
	stack: ['Traefik'],
	email: ['moi@example.com'],
	prenom: 'Adrien',
	securite: 'decideur' as const
};

async function erreurDe(promesse: Promise<unknown>): Promise<ErreurApi> {
	try {
		await promesse;
	} catch (erreur) {
		if (erreur instanceof ErreurApi) return erreur;
		throw erreur;
	}
	throw new Error("l'appel n'a pas échoué");
}

describe('ClientApiResume', () => {
	it('crée, lit, modifie, liste et supprime un profil', async () => {
		const { api } = monter();
		const cree = await api.creerProfil('moi', SAISIE);
		expect(cree).toMatchObject({ username: 'moi', ...SAISIE });
		expect(cree.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);

		const modifie = await api.modifierProfil('moi', {
			...SAISIE,
			stack: [{ nom: 'Keycloak', alias: ['RH-SSO'] }]
		});
		expect(modifie.stack).toEqual([{ nom: 'Keycloak', alias: ['RH-SSO'] }]);
		expect(modifie.id).toBe(cree.id);
		const lu = await api.lireProfil('moi');
		expect(lu.stack).toEqual(modifie.stack);
		expect(lu.id).toBe(cree.id);

		const liste = await api.listerProfils();
		expect(liste).toEqual([
			{
				id: cree.id,
				username: 'moi',
				prenom: 'Adrien',
				email: ['moi@example.com'],
				modifie_le: modifie.modifie_le
			}
		]);

		await api.supprimerProfil('moi');
		expect((await erreurDe(api.lireProfil('moi'))).introuvable).toBe(true);
	});

	it('envoie le jeton en Bearer, le corps en JSON, et encode le username', async () => {
		const { api, fausseApi } = monter();
		await api.creerProfil('moi', SAISIE);
		await erreurDe(api.lireProfil('a/../b'));
		const [creation, lecture] = fausseApi.requetes;
		expect(creation.method).toBe('POST');
		expect(creation.url).toBe('http://api.test/api/v1/profils');
		expect(creation.headers.get('authorization')).toBe(`Bearer ${JETON}`);
		expect(creation.headers.get('content-type')).toBe('application/json');
		expect(await creation.json()).toEqual({ username: 'moi', ...SAISIE });
		expect(lecture.url).toBe('http://api.test/api/v1/profils/a%2F..%2Fb');
	});

	it("n'envoie jamais l'id ni modifie_le dans un corps POST ou PUT", async () => {
		const { api, fausseApi } = monter();
		const cree = await api.creerProfil('moi', SAISIE);
		// Un profil complet passé là où une saisie est attendue : seuls les champs saisis partent.
		await api.modifierProfil('moi', { ...cree, profil: 'RSSI' });
		await api.creerProfil('autre', { ...cree, username: 'ignore' } as typeof SAISIE);
		const corps = await Promise.all(
			fausseApi.requetes.filter((r) => r.method !== 'GET').map((r) => r.json())
		);
		expect(corps).toHaveLength(3);
		for (const c of corps) {
			expect(c).not.toHaveProperty('id');
			expect(c).not.toHaveProperty('modifie_le');
		}
		expect(corps[1]).toEqual({ ...SAISIE, profil: 'RSSI' });
		expect(corps[2].username).toBe('autre');
	});

	it('lit les gabarits', async () => {
		const { api, fausseApi } = monter();
		expect(await api.listerGabarits()).toEqual(GABARITS_DEMO);
		const [lecture] = fausseApi.requetes;
		expect(lecture.method).toBe('GET');
		expect(lecture.url).toBe('http://api.test/api/v1/gabarits');
		expect(lecture.headers.get('authorization')).toBe(`Bearer ${JETON}`);
	});

	it('garde les gabarits en mémoire quelques minutes, sans mémoriser une erreur', async () => {
		const { fausseApi } = monter();
		const h = { t: 1_800_000_000_000 };
		let enPanne = true;
		const api = new ClientApiResume({
			baseUrl: 'http://api.test',
			jeton: JETON,
			dureeGabaritsMs: 5 * 60 * 1000,
			maintenant: () => h.t,
			fetch: (entree, init) =>
				enPanne ? Promise.reject(new TypeError('fetch failed')) : fausseApi.traiter(entree, init)
		});
		const lectures = () => fausseApi.requetes.filter((r) => r.url.endsWith('/api/v1/gabarits')).length;

		// Une erreur n'est pas gardée : l'appel suivant réessaie.
		expect((await erreurDe(api.listerGabarits())).statut).toBe(0);
		enPanne = false;
		expect(await api.listerGabarits()).toEqual(GABARITS_DEMO);
		expect(lectures()).toBe(1);

		h.t += 5 * 60 * 1000 - 1;
		expect(await api.listerGabarits()).toEqual(GABARITS_DEMO);
		expect(lectures()).toBe(1);

		h.t += 1;
		await api.listerGabarits();
		expect(lectures()).toBe(2);
	});

	it('rend une ErreurApi quand un 200 porte un corps illisible', async () => {
		const api = new ClientApiResume({
			baseUrl: 'http://api.test',
			jeton: JETON,
			fetch: async () => new Response('<html>passerelle</html>', { status: 200 })
		});
		const erreur = await erreurDe(api.lirePassage());
		expect(erreur.statut).toBe(0);
		expect(erreur.message).toMatch(/illisible/);
	});

	it('transmet axes et catégories, et les omet quand absents', async () => {
		const { api, fausseApi } = monter();
		const axes = [{ slug: 'cyber', libelle: 'Cybersécurité', description: 'failles et incidents' }];
		const cree = await api.creerProfil('moi', { ...SAISIE, axes, categories: ['Cybersécurité'] });
		expect(cree).toMatchObject({ axes, categories: ['Cybersécurité'] });
		await api.modifierProfil('moi', SAISIE);

		const [creation, modification] = await Promise.all(
			fausseApi.requetes.filter((r) => r.method !== 'GET').map((r) => r.json())
		);
		expect(creation).toEqual({ username: 'moi', ...SAISIE, axes, categories: ['Cybersécurité'] });
		// Une clé absente vaut « réglage par défaut » côté API : aucune n'est inventée.
		expect(modification).not.toHaveProperty('axes');
		expect(modification).not.toHaveProperty('categories');
	});

	it("rend le message de l'API avec son statut : 409, 422, 404", async () => {
		const { api } = monter();
		await api.creerProfil('moi', SAISIE);
		const pris = await erreurDe(api.creerProfil('moi', SAISIE));
		expect(pris.statut).toBe(409);
		expect(pris.message).toBe('username déjà pris : moi');

		const invalide = await erreurDe(api.modifierProfil('moi', { ...SAISIE, email: ['pas-une-adresse'] }));
		expect(invalide.statut).toBe(422);
		expect(invalide.message).toMatch(/adresse invalide/);

		expect((await erreurDe(api.listerJournees('personne'))).statut).toBe(404);
	});

	it('lit les catégories proposées : publiques et privées de la personne, sans propriétaires', async () => {
		const { api, fausseApi } = monter();
		// Le profil n'a pas à exister : la page les propose avant le premier enregistrement.
		const proposees = await api.listerCategories('moi');
		expect(proposees.ouvert).toBe(false);
		const libelles = proposees.categories.map((categorie) => categorie.libelle);
		expect(libelles).toContain('Veille concurrentielle');
		expect(libelles).not.toContain('Veille interne');
		expect(proposees.categories.find((c) => c.libelle === 'Veille concurrentielle')).toEqual({
			libelle: 'Veille concurrentielle',
			description: 'Les mouvements des concurrents.',
			privee: true
		});
		expect(JSON.stringify(proposees)).not.toContain('proprietaires');
		expect(fausseApi.requetes.at(-1)?.url).toBe('http://api.test/api/v1/profils/moi/categories');

		fausseApi.catalogue = null;
		expect(await api.listerCategories('moi')).toEqual({ ouvert: true, categories: [] });
	});

	it('rattache au champ fautif une erreur de validation', async () => {
		const { api } = monter();
		await api.creerProfil('moi', SAISIE);
		const regime = await erreurDe(api.modifierProfil('moi', { ...SAISIE, securite: 'expert' as 'curieux' }));
		expect([regime.statut, regime.champ]).toEqual([422, 'securite']);
		const categorie = await erreurDe(api.modifierProfil('moi', { ...SAISIE, categories: ['Veille interne'] }));
		expect([categorie.statut, categorie.champ]).toEqual([422, 'categories']);
		// Une erreur qui ne nomme pas de champ n'en a pas.
		expect((await erreurDe(api.lireProfil('personne'))).champ).toBeNull();
	});

	it("ne montre pas un 401 comme la faute de l'utilisateur", async () => {
		const { fausseApi } = monter();
		const api = new ClientApiResume({ baseUrl: 'http://api.test', jeton: 'faux', fetch: fausseApi.traiter });
		const erreur = await erreurDe(api.listerProfils());
		expect(erreur.statut).toBe(401);
		expect(erreur.message).toBe('Le service de résumé refuse la connexion du site.');
	});

	it("traduit une API injoignable ou non configurée en statut 0", async () => {
		const enPanne = new ClientApiResume({
			baseUrl: 'http://api.test',
			jeton: JETON,
			fetch: () => Promise.reject(new TypeError('fetch failed'))
		});
		const panne = await erreurDe(enPanne.listerProfils());
		expect(panne.statut).toBe(0);
		expect(panne.message).not.toContain('api.test');

		const sansUrl = new ClientApiResume({ baseUrl: '', jeton: JETON });
		expect((await erreurDe(sansUrl.listerProfils())).message).toMatch(/RSSRESUME_API_URL/);
	});

	it('liste les journées et rend le flux audio avec son Range', async () => {
		const { api, fausseApi } = monter();
		await api.creerProfil('moi', SAISIE);
		const octets = mp3Silencieux(1);
		fausseApi.ajouterAudio('moi', '2026-11-17', 'journee.mp3', octets);
		fausseApi.ajouterAudio('moi', '2026-11-18', 'cyber.mp3', octets);
		expect(await api.listerJournees('moi')).toEqual([
			{ date: '2026-11-18', audios: [{ nom: 'cyber.mp3', taille: octets.length }] },
			{ date: '2026-11-17', audios: [{ nom: 'journee.mp3', taille: octets.length }] }
		]);

		const partiel = await api.audio('moi', '2026-11-17', 'journee.mp3', { range: 'bytes=0-9' });
		expect(partiel.status).toBe(206);
		expect(partiel.headers.get('content-range')).toBe(`bytes 0-9/${octets.length}`);
		expect(fausseApi.requetes.at(-1)?.headers.get('range')).toBe('bytes=0-9');

		const absent = await erreurDe(api.audio('moi', '2026-11-17', 'absent.mp3'));
		expect(absent.introuvable).toBe(true);
	});

	it('lireJournee et lirePassage appellent les bons chemins', async () => {
		const { api, fausseApi } = monter();
		await api.creerProfil('moi', SAISIE);
		fausseApi.ajouterContenu('moi', '2026-11-21', { categories: [] });
		fausseApi.requetes.length = 0;

		const journee = await api.lireJournee('moi', '2026-11-21');
		expect(journee).toMatchObject({ date: '2026-11-21', audios: [], categories: [], montage: null });
		const passage = await api.lirePassage();
		expect(passage).toMatchObject({ heure: '04:00', fuseau: 'Europe/Paris' });
		await erreurDe(api.lireJournee('moi', '../x'));

		const [lecture, annonce, forgee] = fausseApi.requetes;
		expect(lecture.method).toBe('GET');
		expect(lecture.url).toBe('http://api.test/api/v1/profils/moi/journees/2026-11-21');
		expect(lecture.headers.get('authorization')).toBe(`Bearer ${JETON}`);
		expect(annonce.url).toBe('http://api.test/api/v1/passage');
		expect(forgee.url).toBe('http://api.test/api/v1/profils/moi/journees/..%2Fx');
		expect((await erreurDe(api.lireJournee('moi', '2026-11-20'))).introuvable).toBe(true);
	});

	it('envoie le jeton de désabonnement dans un corps JSON, jamais dans le chemin', async () => {
		const { api, fausseApi } = monter();
		await api.creerProfil('moi', SAISIE);
		fausseApi.ajouterDesabonnement('v1.abc.def', 'moi');
		fausseApi.requetes.length = 0;

		expect(await api.lireDesabonnement('v1.abc.def')).toEqual({ username: 'moi', destinataires: 1 });
		expect(await api.desabonner('v1.abc.def')).toEqual({ username: 'moi' });
		expect((await erreurDe(api.desabonner('v1.abc.def'))).introuvable).toBe(true);

		const [lecture, desabonnement] = fausseApi.requetes;
		expect([lecture.method, lecture.url]).toEqual(['POST', 'http://api.test/api/v1/desabonnements/lecture']);
		expect([desabonnement.method, desabonnement.url]).toEqual(['POST', 'http://api.test/api/v1/desabonnements']);
		for (const requete of [lecture, desabonnement]) {
			expect(requete.headers.get('content-type')).toBe('application/json');
			expect(requete.headers.get('authorization')).toBe(`Bearer ${JETON}`);
			expect(await requete.json()).toEqual({ jeton: 'v1.abc.def' });
		}
	});

	it('envoie le jeton de vote dans un corps JSON, et le vote du site au chemin de la journée', async () => {
		const { api, fausseApi } = monter();
		await api.creerProfil('moi', SAISIE);
		fausseApi.ajouterLienRetour('v1.id.2026-11-22.sig', 'moi', '2026-11-22');
		fausseApi.requetes.length = 0;

		expect(await api.lireRetourParLien('v1.id.2026-11-22.sig')).toEqual({
			username: 'moi',
			jour: '2026-11-22',
			retour: null
		});
		const parLien = await api.voterParLien('v1.id.2026-11-22.sig', 'utile', 'Bien.');
		expect(parLien.retour).toMatchObject({ username: 'moi', jour: '2026-11-22', avis: 'utile', commentaire: 'Bien.' });
		expect(await api.lireRetour('moi', '2026-11-22')).toMatchObject({ avis: 'utile' });
		expect(await api.voter('moi', '2026-11-22', 'pas_utile', '')).toMatchObject({ avis: 'pas_utile', commentaire: '' });
		expect(await api.listerRetours()).toHaveLength(1);
		expect((await erreurDe(api.lireRetourParLien('v1.autre.2026-11-22.sig'))).introuvable).toBe(true);

		const [lecture, vote, lu, voteSite, liste] = fausseApi.requetes;
		expect([lecture.method, lecture.url]).toEqual(['POST', 'http://api.test/api/v1/retours/lecture']);
		expect([vote.method, vote.url]).toEqual(['POST', 'http://api.test/api/v1/retours']);
		expect([lu.method, lu.url]).toEqual(['GET', 'http://api.test/api/v1/profils/moi/journees/2026-11-22/retour']);
		expect([voteSite.method, voteSite.url]).toEqual(['PUT', 'http://api.test/api/v1/profils/moi/journees/2026-11-22/retour']);
		expect([liste.method, liste.url]).toEqual(['GET', 'http://api.test/api/v1/retours']);
		// Le jeton ne passe jamais par un chemin : l'API journalise les chemins, pas les corps.
		expect(await lecture.json()).toEqual({ jeton: 'v1.id.2026-11-22.sig' });
		expect(await vote.json()).toEqual({ jeton: 'v1.id.2026-11-22.sig', avis: 'utile', commentaire: 'Bien.' });
		expect(await voteSite.json()).toEqual({ avis: 'pas_utile', commentaire: '' });
		for (const requete of fausseApi.requetes) expect(requete.url).not.toContain('sig');
	});
});
