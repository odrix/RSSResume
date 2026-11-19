import { describe, expect, it } from 'vitest';
import { monter } from './outils-test.js';
import { DUREE_SESSION_MS } from './sessions.js';

const JOUR = 24 * 60 * 60 * 1000;

function horloge(depart = 1_800_000_000_000) {
	const h = { t: depart, maintenant: () => h.t };
	return h;
}

describe('Sessions', () => {
	it('ouvre une session et retrouve son utilisateur', async () => {
		const h = horloge();
		const { creerConfirme, sessions } = monter(h.maintenant);
		const moi = await creerConfirme('moi@example.com', 'moi');
		const { jeton, expireLe } = sessions.ouvrir(moi.id);
		expect(jeton).toMatch(/^[A-Za-z0-9_-]{43}$/);
		expect(expireLe.getTime()).toBe(h.t + DUREE_SESSION_MS);
		expect(sessions.valider(jeton)?.utilisateur.username).toBe('moi');
		expect(sessions.valider('jeton-inconnu')).toBeNull();
	});

	it("refuse la session d'un compte en attente de confirmation", async () => {
		const { comptes, sessions } = monter();
		const enAttente = await comptes.creer('moi@example.com', 'moi', 'une phrase de passe');
		const { jeton } = sessions.ouvrir(enAttente.id);
		expect(sessions.valider(jeton)).toBeNull();
	});

	it('ne stocke pas le jeton en clair', async () => {
		const { base, creerConfirme, sessions } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const { jeton } = sessions.ouvrir(moi.id);
		const ids = base.prepare('SELECT id FROM sessions').all() as { id: string }[];
		expect(ids).toHaveLength(1);
		expect(ids[0].id).not.toBe(jeton);
		expect(ids[0].id).toMatch(/^[0-9a-f]{64}$/);
	});

	it('expire au bout de trente jours et supprime la session', async () => {
		const h = horloge();
		const { base, creerConfirme, sessions } = monter(h.maintenant);
		const moi = await creerConfirme('moi@example.com', 'moi');
		const { jeton } = sessions.ouvrir(moi.id);
		h.t += DUREE_SESSION_MS;
		expect(sessions.valider(jeton)).toBeNull();
		expect(base.prepare('SELECT COUNT(*) AS n FROM sessions').get()).toEqual({ n: 0 });
	});

	it("prolonge une session active à moins de quinze jours de l'échéance", async () => {
		const h = horloge();
		const { creerConfirme, sessions } = monter(h.maintenant);
		const moi = await creerConfirme('moi@example.com', 'moi');
		const { jeton } = sessions.ouvrir(moi.id);

		h.t += 5 * JOUR;
		expect(sessions.valider(jeton)?.prolongee).toBe(false);

		h.t += 20 * JOUR;
		const prolongee = sessions.valider(jeton);
		expect(prolongee?.prolongee).toBe(true);
		expect(prolongee?.expireLe.getTime()).toBe(h.t + DUREE_SESSION_MS);

		h.t += 29 * JOUR;
		expect(sessions.valider(jeton)).not.toBeNull();
	});

	it('ferme une session, et les supprime toutes avec le compte', async () => {
		const { comptes, creerConfirme, sessions } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const a = sessions.ouvrir(moi.id);
		const b = sessions.ouvrir(moi.id);
		sessions.fermer(a.jeton);
		expect(sessions.valider(a.jeton)).toBeNull();
		expect(sessions.valider(b.jeton)).not.toBeNull();
		comptes.supprimer(moi.id);
		expect(sessions.valider(b.jeton)).toBeNull();
	});
});
