import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ContenuJournee from './ContenuJournee.svelte';
import type { ContenuJournee as Contenu } from './journee.js';

function contenu(partiel: Partial<Contenu> = {}): Contenu {
	return {
		date: '2026-11-21',
		audios: [],
		ecoute: null,
		racontees: 0,
		montage: null,
		raison: null,
		categories: [],
		...partiel
	};
}

const HOSTILE = contenu({
	audios: [{ nom: 'cyber.mp3', taille: 10 }],
	categories: [
		{
			categorie: 'Cyber <b>gras</b>',
			racontee: true,
			resume: 'Avant <script>alert(1)</script> après.\n\nSecond paragraphe.',
			audio: 'cyber.mp3',
			ecoute: '5 min',
			articles: [
				{ titre: '<img src=x onerror=alert(1)>', source: 'Flux "piégé"', url: 'javascript:alert(1)' },
				{ titre: 'Sûr', source: 'A', url: 'https://exemple.test/a?x=1&y="2"' }
			],
			a_surveiller: [{ titre: 'Données', source: 'B', url: ' JaVaScRiPt:alert(2)' }]
		}
	]
});

const rendre = (valeur: Contenu, username = 'moi') => render(ContenuJournee, { props: { contenu: valeur, username } }).body;

describe('ContenuJournee', () => {
	it("échappe le texte du modèle et des flux, et ne fait un lien que d'une URL http(s)", () => {
		const html = rendre(HOSTILE);
		expect(html).not.toContain('<script>');
		expect(html).not.toContain('<img');
		expect(html).not.toContain('<b>');
		expect(html).toContain('&lt;script>');
		expect(html).toContain('&lt;img src=x onerror=alert(1)>');
		expect(html).not.toMatch(/href="\s*javascript:/i);
		expect(html.toLowerCase()).not.toContain('javascript:');
		// Le titre sans lien reste affiché, en texte.
		expect(html).toContain('Données');
		expect(html).toMatch(/<a href="https:\/\/exemple\.test\/a\?x=1&amp;y=&quot;2&quot;" rel="noopener noreferrer">Sûr<\/a>/);
		expect(html.match(/<a /g)).toHaveLength(1);
	});

	it('rend chaque paragraphe du résumé et les deux listes', () => {
		const html = rendre(HOSTILE);
		expect(html.match(/<p>/g)?.length).toBe(2);
		expect(html).toContain('Second paragraphe.');
		expect(html).toContain('À lire');
		expect(html).toContain('À surveiller');
	});

	it("pose les lecteurs sur le relais audio du site, celui de la journée en mode global", () => {
		expect(rendre(HOSTILE, 'moi')).toContain('src="/audio/moi/2026-11-21/cyber.mp3"');
		const globale = rendre(
			contenu({
				montage: { audio: 'journee.mp3', ecoute: '12 min' },
				categories: [{ ...HOSTILE.categories[0], audio: null }]
			})
		);
		expect(globale).toContain('src="/audio/moi/2026-11-21/journee.mp3"');
		expect(globale.match(/<audio /g)).toHaveLength(1);
		expect(globale).toContain('12 min');
	});

	it("affiche la raison d'une journée sans article", () => {
		const html = rendre(contenu({ raison: 'Aucun article trouvé pour le vendredi 21 novembre 2026.' }));
		expect(html).toContain('Aucun article trouvé pour le vendredi 21 novembre 2026.');
		expect(html).not.toContain('<audio');
		expect(html).not.toContain('<section');
	});
});
