import { render } from 'svelte/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LimiteurTentatives } from '#lib/server/limiteur.js';
import { envoisDifferes, jetonDuLien, monter, ORIGINE } from '#lib/server/outils-test.js';
import { LIEN_REINITIALISATION_INVALIDE } from '#lib/server/reinitialisation.js';
import Page from './+page.svelte';

const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { load, actions } = await import('./+page.server.js');

const NOUVEAU = 'un tout nouveau mot de passe';

function evenement(jeton: string, motDePasse = NOUVEAU) {
	const url = new URL(`https://site.test/reinitialiser/${jeton}`);
	const effaces: string[] = [];
	return {
		effaces,
		ev: {
			params: { jeton },
			url,
			cookies: { delete: (nom: string) => effaces.push(nom) },
			request: new Request(url, {
				method: 'POST',
				headers: { 'content-type': 'application/x-www-form-urlencoded' },
				body: new URLSearchParams({ motDePasse }).toString()
			})
		} as never
	};
}

function rendre(data: Record<string, unknown>, form: unknown = null): string {
	return render(Page, { props: { data, form } } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

describe('/reinitialiser/[jeton]', () => {
	let env: ReturnType<typeof monter>;
	let limiteParEmail: LimiteurTentatives;
	let jeton: string;
	beforeEach(async () => {
		env = monter();
		await env.creerConfirme('moi@example.com', 'moi');
		env.reinitialisation.demander('moi@example.com', ORIGINE);
		await envoisDifferes();
		jeton = jetonDuLien(env.courrier.envoyes[0].texte);
		limiteParEmail = new LimiteurTentatives(5, 15 * 60 * 1000);
		etat.env = { ...env, limiteParEmail };
	});

	it("l'affichage ne consomme pas le lien ; l'envoi change le mot de passe et mène à la connexion", async () => {
		const data = await load(evenement(jeton).ev);
		expect(data).toEqual({ username: 'moi', invalide: null });
		expect(rendre(data as Record<string, unknown>)).toContain('<form method="POST"');

		const { ev, effaces } = evenement(jeton);
		await expect(actions.default(ev)).rejects.toMatchObject({ status: 303, location: '/connexion?reinitialise=1' });
		expect(effaces).toEqual(['session']);
		expect(await env.comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
	});

	it('lève le blocage de connexion de l’adresse une fois le mot de passe réinitialisé', async () => {
		for (let i = 0; i < 5; i++) limiteParEmail.noter('moi@example.com');
		expect(limiteParEmail.autorise('moi@example.com')).toBe(false);

		await expect(actions.default(evenement(jeton).ev)).rejects.toMatchObject({ status: 303 });
		expect(limiteParEmail.autorise('moi@example.com')).toBe(true);
	});

	it('refuse un lien déjà utilisé, sans formulaire', async () => {
		await expect(actions.default(evenement(jeton).ev)).rejects.toMatchObject({ status: 303 });

		const data = await load(evenement(jeton).ev);
		expect(data).toEqual({ username: null, invalide: LIEN_REINITIALISATION_INVALIDE });
		expect(rendre(data as Record<string, unknown>)).not.toContain('<form');
		const refus = (await actions.default(evenement(jeton, 'encore un autre mot de passe').ev)) as {
			status: number;
			data: { message: string };
		};
		expect(refus.status).toBe(400);
		expect(refus.data.message).toBe(LIEN_REINITIALISATION_INVALIDE);
	});

	it('garde le formulaire quand le mot de passe est trop court', async () => {
		const refus = (await actions.default(evenement(jeton, 'court').ev)) as {
			status: number;
			data: { message: string; champ: string };
		};
		expect(refus.status).toBe(422);
		const html = rendre({ username: 'moi', invalide: null }, refus.data);
		expect(html).toContain('<form method="POST"');
		expect(html).toContain(refus.data.message);
	});
});
