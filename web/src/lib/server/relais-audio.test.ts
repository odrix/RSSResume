import { beforeEach, describe, expect, it } from 'vitest';
import { mp3Silencieux } from '../../../mock/faux-api.js';
import type { Utilisateur } from './comptes.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';
import { RelaisAudio } from './relais-audio.js';

const DATE = '2026-11-18';
const NOM = 'journee.mp3';
const OCTETS = mp3Silencieux(2);

function requete(range?: string): Request {
	return new Request('http://site.test/audio', { headers: range ? { range } : {} });
}

describe('RelaisAudio', () => {
	let env: ReturnType<typeof monter>;
	let relais: RelaisAudio;
	let moi: Utilisateur;
	let autre: Utilisateur;
	let admin: Utilisateur;

	beforeEach(async () => {
		env = monter();
		relais = env.relaisAudio;
		moi = await env.creerConfirme('moi@example.com', 'moi');
		autre = await env.creerConfirme('autre@example.com', 'autre');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		await env.api.creerProfil('moi', { profil: 'CTO', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterAudio('moi', DATE, NOM, OCTETS);
		env.fausseApi.requetes.length = 0;
	});

	it('sert le fichier entier à son propriétaire', async () => {
		const reponse = await relais.servir(moi, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(200);
		expect(reponse.headers.get('content-type')).toBe('audio/mpeg');
		expect(reponse.headers.get('accept-ranges')).toBe('bytes');
		expect(reponse.headers.get('content-length')).toBe(String(OCTETS.length));
		expect(reponse.headers.get('cache-control')).toMatch(/^private/);
		expect(new Uint8Array(await reponse.arrayBuffer())).toEqual(OCTETS);
	});

	it("transmet le Range à l'API et relaie la réponse 206", async () => {
		const reponse = await relais.servir(
			moi,
			{ username: 'moi', date: DATE, nom: NOM },
			requete('bytes=100-199')
		);
		expect(env.fausseApi.requetes[0].headers.get('range')).toBe('bytes=100-199');
		expect(reponse.status).toBe(206);
		expect(reponse.headers.get('content-range')).toBe(`bytes 100-199/${OCTETS.length}`);
		expect(reponse.headers.get('content-length')).toBe('100');
		expect(new Uint8Array(await reponse.arrayBuffer())).toEqual(OCTETS.slice(100, 200));
	});

	it('relaie un 416 pour une plage hors du fichier', async () => {
		const reponse = await relais.servir(
			moi,
			{ username: 'moi', date: DATE, nom: NOM },
			requete(`bytes=${OCTETS.length + 10}-`)
		);
		expect(reponse.status).toBe(416);
		expect(reponse.headers.get('content-range')).toBe(`bytes */${OCTETS.length}`);
	});

	it("laisse l'administrateur écouter les résumés des autres", async () => {
		const reponse = await relais.servir(admin, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(200);
	});

	it("refuse un autre utilisateur par un 404, sans appeler l'API", async () => {
		const reponse = await relais.servir(autre, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(404);
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it('exige une session', async () => {
		const reponse = await relais.servir(null, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(401);
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it.each([
		{ date: '../../x', nom: NOM },
		{ date: DATE, nom: '../journee.mp3' },
		{ date: DATE, nom: '.mp3' },
		{ date: DATE, nom: 'journee.wav' }
	])('refuse un chemin forgé ($date, $nom)', async ({ date, nom }) => {
		const reponse = await relais.servir(admin, { username: 'moi', date, nom }, requete());
		expect(reponse.status).toBe(404);
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it("rend 404 pour un audio que l'API ne connaît pas, 502 pour une API en panne", async () => {
		const absent = await relais.servir(moi, { username: 'moi', date: DATE, nom: 'absent.mp3' }, requete());
		expect(absent.status).toBe(404);

		const { RelaisAudio: Relais } = await import('./relais-audio.js');
		const { ClientApiResume } = await import('./api-resume.js');
		const enPanne = new Relais(
			new ClientApiResume({
				baseUrl: 'http://api.test',
				jeton: 'x',
				fetch: () => Promise.reject(new TypeError('fetch failed'))
			}),
			env.comptes
		);
		const panne = await enPanne.servir(moi, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(panne.status).toBe(502);
	});
});

describe('RelaisAudio, le compteur d’écoutes', () => {
	let env: ReturnType<typeof monter>;
	let moi: Utilisateur;

	const AILLEURS = '2026-11-17';

	beforeEach(async () => {
		env = monter();
		moi = await env.creerConfirme('moi@example.com', 'moi');
		await env.api.creerProfil('moi', { profil: 'CTO', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterAudio('moi', DATE, NOM, OCTETS);
		env.fausseApi.ajouterAudio('moi', DATE, 'autre.mp3', OCTETS);
		env.fausseApi.ajouterAudio('moi', AILLEURS, NOM, OCTETS);
	});

	const servir = (date: string, nom: string, range?: string) =>
		env.relaisAudio.servir(moi, { username: 'moi', date, nom }, requete(range));

	it('compte une écoute après une livraison réussie, une fois par jour et par journée', async () => {
		expect(await servir(DATE, NOM)).toBeInstanceOf(Response);
		expect(env.comptes.ecoutesSeptJours(moi.id)).toBe(1);

		// Le même audio re-servi le même jour, en entier ou par plage : toujours une seule écoute.
		await servir(DATE, NOM);
		await servir(DATE, NOM, 'bytes=0-99');
		// Un autre fichier audio de la même journée ne compte pas non plus.
		await servir(DATE, 'autre.mp3');
		expect(env.comptes.ecoutesSeptJours(moi.id)).toBe(1);

		// Une autre journée audio le même jour d'écoute : une de plus. Le cas d'une même
		// journée servie deux jours différents est couvert dans comptes.test.ts (horloge fixée).
		await servir(AILLEURS, NOM);
		expect(env.comptes.ecoutesSeptJours(moi.id)).toBe(2);
	});

	it('ne compte ni un 404, ni un 416, ni un refus avant appel à l’API', async () => {
		await servir(DATE, 'absent.mp3');
		await servir(DATE, NOM, `bytes=${OCTETS.length + 10}-`);
		await env.relaisAudio.servir(null, { username: 'moi', date: DATE, nom: NOM }, requete());
		await env.relaisAudio.servir(moi, { username: 'moi', date: '2026-13-99', nom: NOM }, requete());
		expect(env.comptes.ecoutesSeptJours(moi.id)).toBe(0);
	});

	it('porte l’écoute sur le profil dont l’audio est servi, même quand un admin écoute', async () => {
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		const reponse = await env.relaisAudio.servir(admin, { username: 'moi', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(200);
		expect(env.comptes.ecoutesSeptJours(moi.id)).toBe(1);
		expect(env.comptes.ecoutesSeptJours(admin.id)).toBe(0);
	});

	it('ne compte pas une écoute dont le profil n’a pas de compte sur le site', async () => {
		await env.api.creerProfil('sanscompte', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterAudio('sanscompte', DATE, NOM, OCTETS);
		const admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		const reponse = await env.relaisAudio.servir(admin, { username: 'sanscompte', date: DATE, nom: NOM }, requete());
		expect(reponse.status).toBe(200);
		const lignes = env.base.prepare('SELECT COUNT(*) AS nombre FROM ecoutes').get() as { nombre: number };
		expect(lignes.nombre).toBe(0);
	});
});
