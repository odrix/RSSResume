import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import { migrer } from './base.js';
import { DUREE_REINITIALISATION_MS, ErreurConfirmation, JetonsEmail, lienReinitialisation } from './jetons-email.js';
import { jetonDuLien, monter, ORIGINE } from './outils-test.js';
import { ErreurMotDePasse, LIEN_REINITIALISATION_INVALIDE } from './reinitialisation.js';

const NOUVEAU = 'un tout nouveau mot de passe';

describe('Reinitialisation', () => {
	it("répond pareil pour une adresse connue, inconnue ou en attente, et n'écrit qu'au compte confirmé", async () => {
		const { reinitialisation, comptes, courrier, creerConfirme } = monter();
		await creerConfirme('moi@example.com', 'moi');
		await comptes.creer('attente@example.com', 'attente', 'une phrase de passe');

		const reponses = [
			reinitialisation.demander('Moi@Example.com', ORIGINE),
			reinitialisation.demander('inconnu@example.com', ORIGINE),
			reinitialisation.demander('attente@example.com', ORIGINE)
		];

		expect(reponses).toEqual([undefined, undefined, undefined]);
		expect(courrier.envoyes.map((m) => m.destinataire)).toEqual(['moi@example.com']);
		expect(courrier.envoyes[0].texte).toContain(`${ORIGINE}/reinitialiser/`);
		expect(courrier.envoyes[0].texte).toContain("dans l'heure");
	});

	it('change le mot de passe et ferme toutes les sessions du compte', async () => {
		const { reinitialisation, comptes, sessions, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const ouverte = sessions.ouvrir(moi.id);
		reinitialisation.demander('moi@example.com', ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);

		expect(reinitialisation.lire(jeton)?.id).toBe(moi.id);
		await reinitialisation.reinitialiser(jeton, NOUVEAU);

		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
		expect(await comptes.authentifier('moi@example.com', 'une phrase de passe')).toBeNull();
		expect(sessions.valider(ouverte.jeton)).toBeNull();
	});

	it('refuse un lien déjà utilisé', async () => {
		const { reinitialisation, comptes, courrier, creerConfirme } = monter();
		await creerConfirme('moi@example.com', 'moi');
		reinitialisation.demander('moi@example.com', ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);
		await reinitialisation.reinitialiser(jeton, NOUVEAU);

		expect(reinitialisation.lire(jeton)).toBeNull();
		await expect(reinitialisation.reinitialiser(jeton, 'encore un autre mot de passe')).rejects.toThrow(
			LIEN_REINITIALISATION_INVALIDE
		);
		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
	});

	it('refuse un lien expiré, au bout d’une heure', async () => {
		const h = { t: 1_800_000_000_000 };
		const { reinitialisation, comptes, courrier, creerConfirme } = monter(() => h.t);
		await creerConfirme('moi@example.com', 'moi');
		reinitialisation.demander('moi@example.com', ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);

		h.t += DUREE_REINITIALISATION_MS - 1;
		expect(reinitialisation.lire(jeton)).not.toBeNull();
		h.t += 1;
		expect(reinitialisation.lire(jeton)).toBeNull();
		await expect(reinitialisation.reinitialiser(jeton, NOUVEAU)).rejects.toBeInstanceOf(ErreurConfirmation);
		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).toBeNull();
	});

	it('garde le lien utilisable quand le nouveau mot de passe est refusé', async () => {
		const { reinitialisation, courrier, creerConfirme } = monter();
		await creerConfirme('moi@example.com', 'moi');
		reinitialisation.demander('moi@example.com', ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);

		await expect(reinitialisation.reinitialiser(jeton, 'court')).rejects.toBeInstanceOf(ErreurMotDePasse);
		expect(reinitialisation.lire(jeton)).not.toBeNull();
	});

	it("n'accepte pas un lien d'un autre objet, ni celui d'une adresse changée depuis", async () => {
		const { reinitialisation, jetons, comptes, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const confirmation = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
		expect(reinitialisation.lire(confirmation)).toBeNull();

		reinitialisation.demander('moi@example.com', ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);
		comptes.changerEmail(moi.id, 'nouvelle@example.com');
		expect(reinitialisation.lire(jeton)).toBeNull();
	});

	it('construit le lien vers la page de réinitialisation', () => {
		expect(lienReinitialisation('https://site.test/', 'abc')).toBe('https://site.test/reinitialiser/abc');
	});

	it('la migration garde les liens en cours et accepte les nouveaux objets', () => {
		const base = new DatabaseSync(':memory:');
		base.exec('PRAGMA foreign_keys = ON');
		migrer(base, 4);
		const id = Number(
			base
				.prepare('INSERT INTO comptes (email, username, hash, cree_le, confirme_le) VALUES (?, ?, ?, ?, ?)')
				.run('moi@example.com', 'moi', 'x', '2026-01-01', '2026-01-01').lastInsertRowid
		);
		const jetons = new JetonsEmail(base);
		const ancien = jetons.emettre(id, 'moi@example.com', 'destinataire');
		migrer(base);

		expect(jetons.lire(ancien)?.objet).toBe('destinataire');
		expect(jetons.lire(jetons.emettre(id, 'moi@example.com', 'reinitialisation'))?.objet).toBe('reinitialisation');
		expect(jetons.lire(jetons.emettre(id, 'autre@example.com', 'adresse'))?.objet).toBe('adresse');
	});
});
