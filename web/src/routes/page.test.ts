import { render } from 'svelte/server';

import { describe, expect, it, vi } from 'vitest';

import Page from './+page.svelte';

/* Si la page d'accueil appelait un jour l'API ou le contexte, ce mock lèverait : l'exemple
 * est un fichier statique, la page se sert sans API ni session. */
vi.mock('#lib/server/contexte.js', () => ({
	contexte: () => {
		throw new Error("la page d'accueil ne doit pas appeler l'API");
	}
}));

const { load } = await import('./+page.server.js');

/** Des `locals` dont toute lecture autre que `utilisateur` lève : aucune session ne doit être lue. */
const localsSansSession = { utilisateur: null } as never;

function rendre(data: Record<string, unknown>): string {
	return render(Page, { props: { data, form: null } } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

async function chargerSansConnexion() {
	return (await load({ locals: localsSansSession } as never)) as Record<string, unknown>;
}

describe('/', () => {
	it("montre l'extrait de lettre et un lecteur audio sans connexion (a)", async () => {
		const data = await chargerSansConnexion();

		// L'extrait vient du fichier statique versionné, pas de l'API.
		expect(typeof data.extraitLettre).toBe('string');
		expect(data.extraitLettre).toContain('catégorie « Tech »');
		expect(data.audioExemple).toBe('/exemple/extrait.mp3');

		const html = rendre(data);
		expect(html).toContain('Un exemple de ce que vous recevrez');
		expect(html).toContain('Une nouvelle version du langage Python');
		expect(html).toContain('<audio controls="" src="/exemple/extrait.mp3">');
		// Les boutons inscription/connexion sont conservés.
		expect(html).toContain('href="/inscription"');
		expect(html).toContain('href="/connexion"');
	});

	it('met la mention bêta avant le bloc exemple dans le DOM, donc visible sans défiler (b)', async () => {
		const html = rendre(await chargerSansConnexion());
		const beta = html.indexOf('Service en <strong>bêta</strong>');
		const exemple = html.indexOf('Un exemple de ce que vous recevrez');
		expect(beta).toBeGreaterThanOrEqual(0);
		expect(exemple).toBeGreaterThan(beta);
		// La page dit ce qu'on reçoit, à quelle heure, et que les retours décident de la suite.
		expect(html).toContain('le lendemain matin par email');
		expect(html).toContain('vos retours qui décident de la suite');
	});

	it("ne dépend ni de l'API ni d'une session (c) : le load ne lit que le disque et locals.utilisateur", async () => {
		// `contexte()` lèverait via le mock ; un `locals` piégé lèverait sur toute autre clé.
		const piege = new Proxy(
			{ utilisateur: null },
			{
				get(cible, cle) {
					if (cle === 'utilisateur') return cible.utilisateur;
					throw new Error(`la page d'accueil ne doit lire aucune autre clé de locals (${String(cle)})`);
				}
			}
		) as never;
		const data = (await load({ locals: piege } as never)) as { extraitLettre: string };
		expect(data.extraitLettre.length).toBeGreaterThan(0);
	});

	it('redirige un visiteur connecté vers /resumes (303)', async () => {
		const connecte = { utilisateur: { pourPage: () => ({}) } } as never;
		// `load` est synchrone : la redirection est levée, pas rejetée.
		let erreur: unknown;
		try {
			await load({ locals: connecte } as never);
		} catch (e) {
			erreur = e;
		}
		expect(erreur).toMatchObject({ status: 303, location: '/resumes' });
	});
});
