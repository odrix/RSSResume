import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it, vi } from 'vitest';
import { migrer } from './base.js';
import { DUREE_REINITIALISATION_MS, ErreurConfirmation, JetonsEmail, lienReinitialisation } from './jetons-email.js';
import { envoisDifferes, jetonDuLien, monter, ORIGINE } from './outils-test.js';
import { ErreurMotDePasse, LIEN_REINITIALISATION_INVALIDE } from './reinitialisation.js';

const NOUVEAU = 'un tout nouveau mot de passe';

type Env = ReturnType<typeof monter>;

/** Demande un lien et rend son jeton, une fois l'envoi différé parti. */
async function lienRecu({ reinitialisation, courrier }: Env, email = 'moi@example.com'): Promise<string> {
	reinitialisation.demander(email, ORIGINE);
	await envoisDifferes();
	return jetonDuLien(courrier.envoyes.at(-1)!.texte);
}

describe('Reinitialisation', () => {
	it("répond pareil pour une adresse connue, inconnue ou en attente, et n'écrit qu'au compte confirmé", async () => {
		const { reinitialisation, comptes, courrier, base, creerConfirme } = monter();
		await creerConfirme('moi@example.com', 'moi');
		await comptes.creer('attente@example.com', 'attente', 'une phrase de passe');

		const reponses = [
			reinitialisation.demander('Moi@Example.com', ORIGINE),
			reinitialisation.demander('inconnu@example.com', ORIGINE),
			reinitialisation.demander('attente@example.com', ORIGINE)
		];

		expect(reponses).toEqual([undefined, undefined, undefined]);
		// Rien n'est fait avant la réponse, pas même l'écriture du jeton : le temps de
		// réponse d'une adresse connue est celui d'une inconnue.
		expect(base.prepare('SELECT COUNT(*) AS n FROM jetons_email').get()).toEqual({ n: 0 });
		expect(courrier.envoyes).toEqual([]);
		await envoisDifferes();
		expect(courrier.envoyes.map((m) => m.destinataire)).toEqual(['moi@example.com']);
		expect(courrier.envoyes[0].texte).toContain(`${ORIGINE}/reinitialiser/`);
		expect(courrier.envoyes[0].texte).toContain("dans l'heure");
	});

	it('change le mot de passe et ferme toutes les sessions du compte', async () => {
		const env = monter();
		const { reinitialisation, comptes, sessions, creerConfirme } = env;
		const moi = await creerConfirme('moi@example.com', 'moi');
		const ouverte = sessions.ouvrir(moi.id);
		const jeton = await lienRecu(env);

		expect(reinitialisation.lire(jeton)?.id).toBe(moi.id);
		await reinitialisation.reinitialiser(jeton, NOUVEAU);

		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
		expect(await comptes.authentifier('moi@example.com', 'une phrase de passe')).toBeNull();
		expect(sessions.valider(ouverte.jeton)).toBeNull();
	});

	it('refuse un lien déjà utilisé', async () => {
		const env = monter();
		const { reinitialisation, comptes, creerConfirme } = env;
		await creerConfirme('moi@example.com', 'moi');
		const jeton = await lienRecu(env);
		await reinitialisation.reinitialiser(jeton, NOUVEAU);

		expect(reinitialisation.lire(jeton)).toBeNull();
		await expect(reinitialisation.reinitialiser(jeton, 'encore un autre mot de passe')).rejects.toThrow(
			LIEN_REINITIALISATION_INVALIDE
		);
		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
	});

	it('refuse un lien expiré, au bout d’une heure', async () => {
		const h = { t: 1_800_000_000_000 };
		const env = monter(() => h.t);
		const { reinitialisation, comptes, creerConfirme } = env;
		await creerConfirme('moi@example.com', 'moi');
		const jeton = await lienRecu(env);

		h.t += DUREE_REINITIALISATION_MS - 1;
		expect(reinitialisation.lire(jeton)).not.toBeNull();
		h.t += 1;
		expect(reinitialisation.lire(jeton)).toBeNull();
		await expect(reinitialisation.reinitialiser(jeton, NOUVEAU)).rejects.toBeInstanceOf(ErreurConfirmation);
		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).toBeNull();
	});

	it('garde le lien utilisable quand le nouveau mot de passe est refusé', async () => {
		const env = monter();
		const { reinitialisation, creerConfirme } = env;
		await creerConfirme('moi@example.com', 'moi');
		const jeton = await lienRecu(env);

		await expect(reinitialisation.reinitialiser(jeton, 'court')).rejects.toBeInstanceOf(ErreurMotDePasse);
		expect(reinitialisation.lire(jeton)).not.toBeNull();
	});

	it("n'accepte pas un lien d'un autre objet, ni celui d'une adresse changée depuis", async () => {
		const env = monter();
		const { reinitialisation, jetons, comptes, creerConfirme } = env;
		const moi = await creerConfirme('moi@example.com', 'moi');
		const confirmation = jetons.emettre(moi.id, 'moi@example.com', 'inscription');
		expect(reinitialisation.lire(confirmation)).toBeNull();

		const jeton = await lienRecu(env);
		comptes.changerEmail(moi.id, 'nouvelle@example.com');
		expect(reinitialisation.lire(jeton)).toBeNull();
	});

	it("révoque, au nouveau mot de passe, les autres liens de réinitialisation et d'adresse", async () => {
		const env = monter();
		const { reinitialisation, jetons, creerConfirme } = env;
		const moi = await creerConfirme('moi@example.com', 'moi');
		const premier = await lienRecu(env);
		const adresse = jetons.emettre(moi.id, 'inconnu@example.com', 'adresse');
		// Un second lien remplace le premier ; c'est lui qui sert.
		const second = await lienRecu(env);
		expect(reinitialisation.lire(premier)).toBeNull();

		await reinitialisation.reinitialiser(second, NOUVEAU);
		expect(jetons.lire(adresse)).toBeNull();
		expect(env.base.prepare('SELECT COUNT(*) AS n FROM jetons_email').get()).toEqual({ n: 0 });
	});

	it("journalise un échec de l'envoi différé au lieu de le laisser en rejet non géré", async () => {
		const env = monter();
		await env.creerConfirme('moi@example.com', 'moi');
		const journal = vi.spyOn(console, 'error').mockImplementation(() => {});
		vi.spyOn(env.jetons, 'emettre').mockImplementation(() => {
			throw new Error('database is locked');
		});
		try {
			env.reinitialisation.demander('moi@example.com', ORIGINE);
			await envoisDifferes();
			await envoisDifferes();
			expect(journal).toHaveBeenCalledWith(
				expect.stringContaining('Lien de réinitialisation de moi non envoyé'),
				expect.any(Error)
			);
			expect(env.courrier.envoyes).toEqual([]);
		} finally {
			vi.restoreAllMocks();
		}
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
