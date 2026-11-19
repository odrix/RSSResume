import { expect, it } from 'vitest';
import { DUREE_JETON_EMAIL_MS, lienConfirmation } from './jetons-email.js';
import { monter } from './outils-test.js';

it('émet un jeton de 256 bits dont seule l’empreinte est en base', async () => {
	const { base, jetons, creerConfirme } = monter();
	const moi = await creerConfirme('moi@example.com', 'moi');
	const jeton = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
	expect(jeton).toMatch(/^[A-Za-z0-9_-]{43}$/);
	const ids = base.prepare('SELECT id FROM jetons_email').all() as { id: string }[];
	expect(ids).toEqual([{ id: expect.stringMatching(/^[0-9a-f]{64}$/) }]);
	expect(ids[0].id).not.toBe(jeton);
	expect(jetons.lire(jeton)).toEqual({ compteId: moi.id, email: 'moi@example.com', objet: 'inscription' });
});

it('expire au bout de 24 heures, se consomme, et cède la place au suivant', async () => {
	const h = { t: 1_800_000_000_000 };
	const { jetons, creerConfirme } = monter(() => h.t);
	const moi = await creerConfirme('moi@example.com', 'moi');

	const a = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
	const b = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
	expect(jetons.lire(a)).toBeNull();
	expect(jetons.lire(b)).not.toBeNull();

	h.t += DUREE_JETON_EMAIL_MS - 1;
	expect(jetons.lire(b)).not.toBeNull();
	h.t += 1;
	expect(jetons.lire(b)).toBeNull();

	const c = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
	jetons.consommer(c);
	expect(jetons.lire(c)).toBeNull();
});

it('construit le lien vers la page de confirmation', () => {
	expect(lienConfirmation('https://site.test/', 'abc')).toBe('https://site.test/confirmer/abc');
});
