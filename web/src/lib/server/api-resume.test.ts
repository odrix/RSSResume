import { describe, expect, it } from 'vitest';
import { mp3Silencieux } from '../../../mock/faux-api.js';
import { ClientApiResume, ErreurApi } from './api-resume.js';
import { JETON, monter } from './outils-test.js';

const SAISIE = { profil: 'CTO', stack: ['Traefik'], email: ['moi@example.com'], prenom: 'Adrien' };

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
});
