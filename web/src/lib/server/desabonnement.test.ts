import { describe, expect, it } from 'vitest';
import { ErreurDesabonnement, LIEN_DESABONNEMENT_INVALIDE } from './desabonnement.js';
import { monter } from './outils-test.js';

const JETON = 'v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71.empreinte.signature';

async function avecProfil() {
	const env = monter();
	await env.api.creerProfil('bea', {
		profil: 'Veille',
		stack: [],
		email: ['b@example.com', 'c@example.com'],
		prenom: '',
		securite: 'exploitant'
	});
	env.fausseApi.ajouterDesabonnement(JETON, 'bea');
	return env;
}

describe('Desabonnement', () => {
	it('lit ce que le lien désabonnerait sans rien changer', async () => {
		const { desabonnement, api } = await avecProfil();

		expect(await desabonnement.lire(JETON)).toEqual({ username: 'bea', destinataires: 2 });
		expect((await api.lireProfil('bea')).email).toEqual(['b@example.com', 'c@example.com']);
	});

	it('vide les destinataires, puis refuse le même lien', async () => {
		const { desabonnement, api } = await avecProfil();

		expect(await desabonnement.appliquer(JETON)).toEqual({ username: 'bea' });
		expect((await api.lireProfil('bea')).email).toEqual([]);

		await expect(desabonnement.appliquer(JETON)).rejects.toThrow(LIEN_DESABONNEMENT_INVALIDE);
		expect(await desabonnement.lire(JETON)).toBeNull();
	});

	it("écarte sans appel ce qui ne peut pas être un jeton", async () => {
		const { desabonnement, fausseApi } = await avecProfil();
		const avant = fausseApi.requetes.length;

		for (const jeton of ['', 'sansPoint', 'a.b/c', 'a..b', `a.${'x'.repeat(5000)}`]) {
			expect(await desabonnement.lire(jeton)).toBeNull();
			await expect(desabonnement.appliquer(jeton)).rejects.toBeInstanceOf(ErreurDesabonnement);
		}
		expect(fausseApi.requetes.length).toBe(avant);
	});

	it("laisse passer le jeton d'une lettre à de nombreux destinataires", async () => {
		const { desabonnement, fausseApi } = await avecProfil();
		// Huit caractères d'empreinte par adresse : cinquante destinataires font 400 caractères.
		const long = `v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71.${'AbCd-_12'.repeat(50)}.${'s'.repeat(43)}`;
		fausseApi.ajouterDesabonnement(long, 'bea');

		expect(await desabonnement.lire(long)).toEqual({ username: 'bea', destinataires: 2 });
	});

	it("rend le message de l'API quand elle ne répond pas", async () => {
		const { desabonnement, fausseApi } = await avecProfil();
		fausseApi.jeton = 'autre';

		await expect(desabonnement.lire(JETON)).rejects.toBeInstanceOf(ErreurDesabonnement);
		await expect(desabonnement.appliquer(JETON)).rejects.toBeInstanceOf(ErreurDesabonnement);
	});
});
