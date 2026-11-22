import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import Page from './+page.svelte';

const PASSAGE = { heure: '04:00', fuseau: 'Europe/Paris', prochain: '2026-11-23T04:00:00+01:00' };

function rendre(data: Record<string, unknown>): string {
	const props = {
		data: { username: 'moi', proprietaire: true, journees: [], passage: null, erreur: null, ...data },
		params: { username: String(data.username ?? 'moi') }
	};
	// La page n'attend que `data` ; le reste des props de SvelteKit n'y sert pas.
	return render(Page, { props } as unknown as Parameters<typeof render<typeof Page>>[1]).body;
}

describe('page des résumés, état vide', () => {
	it("annonce le passage, et non une heure d'arrivée, à son propriétaire", () => {
		const html = rendre({ passage: PASSAGE });
		expect(html).toContain('Votre premier résumé arrivera après le passage du lundi 23 novembre à 04:00.');
	});

	it("parle de l'autre personne à un administrateur", () => {
		const html = rendre({ username: 'bea', proprietaire: false, passage: PASSAGE });
		expect(html).toContain('Le premier résumé de bea arrivera après le passage du lundi 23 novembre à 04:00.');
		expect(html).not.toContain('Votre premier');
	});

	it('garde la phrase sans heure quand le passage est inconnu', () => {
		expect(rendre({})).toContain('Le premier arrivera après le prochain passage quotidien.');
	});

	it('pointe chaque journée vers sa page de lecture', () => {
		const html = rendre({ journees: [{ date: '2026-11-21', audios: [] }] });
		expect(html).toContain('href="/resumes/moi/2026-11-21"');
	});
});
