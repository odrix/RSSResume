import { beforeEach, describe, expect, it } from 'vitest';
import { mp3Silencieux } from '../../../mock/faux-api.js';
import { ClientApiResume } from './api-resume.js';
import type { Utilisateur } from './comptes.js';
import { ConsultationResumes } from './consultation.js';
import { EMAIL_ADMIN, JETON, monter } from './outils-test.js';

const DATE = '2026-11-21';
const CONTENU = {
	ecoute: '5 min',
	racontees: 1,
	categories: [
		{
			categorie: 'Cybersécurité',
			racontee: true,
			resume: 'Le résumé.',
			audio: 'cyber.mp3',
			ecoute: '5 min',
			articles: [
				{ titre: 'Sûr', source: 'A', url: 'https://exemple.test/a' },
				{ titre: 'Piégé', source: 'B', url: 'javascript:alert(1)' }
			],
			a_surveiller: [{ titre: 'Données', source: 'C', url: 'data:text/html,x' }]
		}
	]
};

describe('ConsultationResumes', () => {
	let env: ReturnType<typeof monter>;
	let consultation: ConsultationResumes;
	let moi: Utilisateur;
	let autre: Utilisateur;
	let admin: Utilisateur;

	beforeEach(async () => {
		env = monter();
		consultation = new ConsultationResumes(env.api);
		moi = await env.creerConfirme('moi@example.com', 'moi');
		autre = await env.creerConfirme('autre@example.com', 'autre');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		await env.api.creerProfil('moi', { profil: 'CTO', stack: [], email: [], prenom: '' });
		env.fausseApi.ajouterAudio('moi', DATE, 'cyber.mp3', mp3Silencieux(1));
		env.fausseApi.ajouterContenu('moi', DATE, CONTENU);
		env.fausseApi.requetes.length = 0;
	});

	it('rend la journée à son propriétaire', async () => {
		const contenu = await consultation.journee(moi, 'moi', DATE);
		expect(contenu?.date).toBe(DATE);
		expect(contenu?.categories[0].resume).toBe('Le résumé.');
		expect(contenu?.audios).toEqual([{ nom: 'cyber.mp3', taille: mp3Silencieux(1).length }]);
		expect(env.fausseApi.requetes.at(-1)?.url).toBe(`http://api.test/api/v1/profils/moi/journees/${DATE}`);
	});

	it("la rend à l'administrateur", async () => {
		expect((await consultation.journee(admin, 'moi', DATE))?.date).toBe(DATE);
	});

	it("rend null à un autre utilisateur sans appeler l'API", async () => {
		expect(await consultation.journee(autre, 'moi', DATE)).toBeNull();
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it("refuse une date mal formée sans appeler l'API", async () => {
		for (const date of ['../../x', '20261121', '2026-11-21/audios/cyber.mp3', '']) {
			expect(await consultation.journee(admin, 'moi', date), date).toBeNull();
		}
		expect(await consultation.journee(admin, '../moi', DATE)).toBeNull();
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it("rend null pour une journée que l'API ne connaît pas", async () => {
		expect(await consultation.journee(moi, 'moi', '2026-11-20')).toBeNull();
	});

	it('retire les liens qui ne sont pas http(s), même si l’API les laissait passer', async () => {
		const contenu = await consultation.journee(moi, 'moi', DATE);
		const categorie = contenu!.categories[0];
		expect(categorie.articles.map((lien) => lien.url)).toEqual(['https://exemple.test/a', null]);
		expect(categorie.a_surveiller.map((lien) => lien.url)).toEqual([null]);
		expect(categorie.articles[1].titre).toBe('Piégé');
	});

	it('une journée sans audio a son contenu', async () => {
		env.fausseApi.ajouterContenu('moi', '2026-11-19', {});
		expect(await env.api.listerJournees('moi')).toContainEqual({ date: '2026-11-19', audios: [] });
		const contenu = await consultation.journee(moi, 'moi', '2026-11-19');
		expect(contenu?.audios).toEqual([]);
		expect(contenu?.categories).toEqual([]);
		expect(contenu?.raison).toMatch(/^Aucun article trouvé/);
	});

	it("annonce le passage, ou null si l'API ne répond pas", async () => {
		const passage = await consultation.passage();
		expect(passage).toMatchObject({ heure: '04:00', fuseau: 'Europe/Paris' });
		const prochain = new Date(passage!.prochain);
		expect(prochain.getTime()).toBeGreaterThan(Date.now());
		expect(prochain.getTime() - Date.now()).toBeLessThanOrEqual(86_400_000);
		expect(passage!.prochain).toMatch(/T04:00:00\+0[12]:00$/);

		const enPanne = new ConsultationResumes(
			new ClientApiResume({
				baseUrl: 'http://api.test',
				jeton: JETON,
				fetch: () => Promise.reject(new TypeError('fetch failed'))
			})
		);
		expect(await enPanne.passage()).toBeNull();
	});
});
