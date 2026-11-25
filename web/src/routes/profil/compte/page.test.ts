import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Utilisateur } from '#lib/server/comptes.js';
import { LimiteurTentatives } from '#lib/server/limiteur.js';
import { jetonDuLien, monter } from '#lib/server/outils-test.js';

const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load, actions } = await import('./+page.server.js');
const confirmation = await import('../../confirmer/[jeton]/+page.server.js');

const ACTUEL = 'une phrase de passe';

function evenement(utilisateur: Utilisateur | null, corps: Record<string, string> = {}, session?: string) {
	const url = new URL('https://site.test/profil/compte');
	return {
		url,
		locals: { utilisateur },
		cookies: { get: () => session },
		request: new Request(url, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams(corps).toString()
		})
	} as never;
}

describe('/profil/compte', () => {
	let env: ReturnType<typeof monter>;
	let moi: Utilisateur;
	beforeEach(async () => {
		env = monter();
		moi = await env.creerConfirme('moi@example.com', 'moi');
		etat.env = {
			...env,
			limiteParEmail: new LimiteurTentatives(5, 15 * 60 * 1000),
			limiteRenvoisParEmail: new LimiteurTentatives(3, 60 * 60 * 1000)
		};
	});

	it('exige une connexion', async () => {
		await expect(Promise.resolve().then(() => load(evenement(null)))).rejects.toMatchObject({ status: 303 });
	});

	it('refuse le changement de mot de passe sans le bon mot de passe actuel, puis bloque', async () => {
		const corps = { motDePasseActuel: 'pas le bon du tout', nouveauMotDePasse: 'un tout nouveau mot de passe' };
		const refus = (await actions.motDePasse(evenement(moi, corps))) as { status: number; data: { champ: string } };
		expect(refus.status).toBe(403);
		expect(refus.data.champ).toBe('motDePasseActuel');
		expect(await env.comptes.authentifier('moi@example.com', ACTUEL)).not.toBeNull();

		for (let i = 0; i < 4; i++) await actions.motDePasse(evenement(moi, corps));
		const bloque = (await actions.motDePasse(
			evenement(moi, { ...corps, motDePasseActuel: ACTUEL })
		)) as { status: number };
		expect(bloque.status).toBe(429);
	});

	it('change le mot de passe avec le bon mot de passe actuel, en gardant sa session', async () => {
		const ici = env.sessions.ouvrir(moi.id);
		const resultat = await actions.motDePasse(
			evenement(moi, { motDePasseActuel: ACTUEL, nouveauMotDePasse: 'un tout nouveau mot de passe' }, ici.jeton)
		);
		expect(resultat).toMatchObject({ formulaire: 'motDePasse', succes: expect.any(String) });
		expect(env.sessions.valider(ici.jeton)).not.toBeNull();
	});

	it("n'applique la nouvelle adresse qu'une fois le lien confirmé", async () => {
		const resultat = await actions.adresse(evenement(moi, { email: 'nouvelle@example.com', motDePasse: ACTUEL }));
		expect(resultat).toMatchObject({ formulaire: 'adresse' });
		expect(env.comptes.parId(moi.id)?.email).toBe('moi@example.com');

		const jeton = jetonDuLien(env.courrier.envoyes.at(-1)!.texte);
		const page = { params: { jeton }, url: new URL(`https://site.test/confirmer/${jeton}`) } as never;
		expect(await confirmation.load(page)).toMatchObject({ objet: 'adresse', email: 'nouvelle@example.com' });
		expect(env.comptes.parId(moi.id)?.email).toBe('moi@example.com');

		expect(await confirmation.actions.default(page)).toMatchObject({ confirme: expect.stringContaining('nouvelle@example.com') });
		expect(env.comptes.parId(moi.id)?.email).toBe('nouvelle@example.com');
	});

	it('remet à zéro les échecs de l’adresse dès que le mot de passe actuel est vérifié', async () => {
		const limite = (etat.env as { limiteParEmail: LimiteurTentatives }).limiteParEmail;
		const faux = { motDePasseActuel: 'pas le bon du tout', nouveauMotDePasse: 'un tout nouveau mot de passe' };
		for (let i = 0; i < 4; i++) await actions.motDePasse(evenement(moi, faux));

		// Le bon mot de passe, même avec un nouveau refusé, prouve qu'on parle au titulaire.
		await actions.motDePasse(evenement(moi, { motDePasseActuel: ACTUEL, nouveauMotDePasse: 'court' }));
		for (let i = 0; i < 4; i++) limite.noter('moi@example.com');
		expect(limite.autorise('moi@example.com')).toBe(true);

		await actions.adresse(evenement(moi, { email: 'nouvelle@example.com', motDePasse: ACTUEL }));
		limite.noter('moi@example.com');
		expect(limite.autorise('moi@example.com')).toBe(true);
	});

	it("refuse le changement d'adresse sans le bon mot de passe", async () => {
		const refus = (await actions.adresse(
			evenement(moi, { email: 'nouvelle@example.com', motDePasse: 'pas le bon du tout' })
		)) as { status: number; data: { email: string } };
		expect(refus.status).toBe(403);
		expect(refus.data.email).toBe('nouvelle@example.com');
		expect(env.courrier.envoyes).toEqual([]);
	});
});
