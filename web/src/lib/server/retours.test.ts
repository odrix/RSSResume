import { describe, expect, it } from 'vitest';
import { LONGUEUR_MAX_COMMENTAIRE } from '#lib/retour.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';
import { ErreurRetour, LIEN_RETOUR_INVALIDE, saisieRetour } from './retours.js';

const JETON = 'v1.0b6f7e0a-3c55-4a8e-9a43-1f2d0c9e8b71.2026-11-22.signature';
const JOUR = '2026-11-22';

async function avecProfil() {
	const env = monter();
	await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
	env.fausseApi.ajouterLienRetour(JETON, 'bea', JOUR);
	return env;
}

function formulaire(champs: Record<string, string>): FormData {
	const form = new FormData();
	for (const [nom, valeur] of Object.entries(champs)) form.set(nom, valeur);
	return form;
}

describe('saisieRetour', () => {
	it('lit l’avis et le commentaire, fins de ligne ramenées à \\n', () => {
		expect(saisieRetour(formulaire({ avis: 'pas_utile', commentaire: '  Trop long.\r\nMerci ' }))).toEqual({
			avis: 'pas_utile',
			commentaire: 'Trop long.\nMerci'
		});
		expect(saisieRetour(formulaire({ avis: 'utile' }))).toEqual({ avis: 'utile', commentaire: '' });
	});

	it('compte en caractères comme l’API : 2 000 emojis passent, un de plus non', () => {
		const emojis = '👍'.repeat(LONGUEUR_MAX_COMMENTAIRE);
		expect(emojis.length).toBe(2 * LONGUEUR_MAX_COMMENTAIRE);
		expect(saisieRetour(formulaire({ avis: 'utile', commentaire: emojis })).commentaire).toBe(emojis);
		expect(() => saisieRetour(formulaire({ avis: 'utile', commentaire: `${emojis}x` }))).toThrow(ErreurRetour);
	});

	it('refuse un avis inconnu', () => {
		for (const avis of ['', 'UTILE', 'moyen']) {
			expect(() => saisieRetour(formulaire({ avis }))).toThrow(ErreurRetour);
		}
		expect(() => saisieRetour(new FormData())).toThrow(ErreurRetour);
	});
});

describe('Retours', () => {
	it('lit le lien sans voter, puis vote ; un second vote remplace le premier', async () => {
		const { retours, fausseApi } = await avecProfil();

		expect(await retours.lireLien(JETON)).toEqual({ username: 'bea', jour: JOUR, retour: null });
		expect(fausseApi.retours.size).toBe(0);

		await retours.voterParLien(JETON, { avis: 'utile', commentaire: 'Bien.' });
		const second = await retours.voterParLien(JETON, { avis: 'pas_utile', commentaire: 'Non.' });

		expect(second.retour).toMatchObject({ avis: 'pas_utile', commentaire: 'Non.' });
		expect(fausseApi.retours.size).toBe(1);
		expect((await retours.lireLien(JETON))?.retour?.commentaire).toBe('Non.');
	});

	it('refuse un lien inconnu, et écarte sans appel ce qui ne peut pas être un jeton', async () => {
		const { retours, fausseApi } = await avecProfil();

		expect(await retours.lireLien('v1.inconnu.2026-11-22.x')).toBeNull();
		await expect(retours.voterParLien('v1.inconnu.2026-11-22.x', { avis: 'utile', commentaire: '' })).rejects.toThrow(
			LIEN_RETOUR_INVALIDE
		);

		const avant = fausseApi.requetes.length;
		for (const jeton of ['', 'sansPoint', 'a.b/c', 'a..b', `a.${'x'.repeat(300)}`]) {
			expect(await retours.lireLien(jeton)).toBeNull();
			await expect(retours.voterParLien(jeton, { avis: 'utile', commentaire: '' })).rejects.toBeInstanceOf(ErreurRetour);
		}
		expect(fausseApi.requetes.length).toBe(avant);
	});

	it("ne laisse voter sur le site que le propriétaire, pas un admin qui consulte la journée d'un autre", async () => {
		const { retours, fausseApi, creerConfirme } = await avecProfil();
		const bea = await creerConfirme('bea@example.com', 'bea');
		const admin = await creerConfirme(EMAIL_ADMIN, 'chef');
		const autre = await creerConfirme('autre@example.com', 'autre');
		const avant = fausseApi.requetes.length;

		for (const quelquun of [admin, autre]) {
			expect(await retours.voter(quelquun, 'bea', JOUR, { avis: 'utile', commentaire: '' })).toBeNull();
			expect(await retours.lire(quelquun, 'bea', JOUR)).toBeNull();
		}
		expect(fausseApi.requetes.length).toBe(avant);
		expect(fausseApi.retours.size).toBe(0);

		expect(await retours.lire(bea, 'bea', JOUR)).toBeNull();
		expect(await retours.voter(bea, 'bea', JOUR, { avis: 'utile', commentaire: 'Oui.' })).toMatchObject({
			avis: 'utile',
			commentaire: 'Oui.'
		});
		expect(await retours.lire(bea, 'bea', JOUR)).toMatchObject({ commentaire: 'Oui.' });
	});

	it("rend le refus de l'API sous forme d'ErreurRetour", async () => {
		const { retours, creerConfirme } = await avecProfil();
		const bea = await creerConfirme('bea@example.com', 'bea');

		await expect(
			retours.voter(bea, 'bea', JOUR, { avis: 'utile', commentaire: 'x'.repeat(LONGUEUR_MAX_COMMENTAIRE + 1) })
		).rejects.toBeInstanceOf(ErreurRetour);
	});
});
