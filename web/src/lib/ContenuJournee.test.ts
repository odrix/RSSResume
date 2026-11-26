import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ContenuJournee from './ContenuJournee.svelte';
import type { ContenuJournee as Contenu } from './journee.js';
import { CLE_LECTEUR, LecteurAudio, PisteAudio } from './lecteur.svelte.js';

function contenu(partiel: Partial<Contenu> = {}): Contenu {
	return {
		date: '2026-11-21',
		audios: [],
		ecoute: null,
		racontees: 0,
		montage: null,
		raison: null,
		en_cours: false,
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

const rendre = (valeur: Contenu, username = 'moi', lecteur = new LecteurAudio()) =>
	render(ContenuJournee, {
		props: { contenu: valeur, username },
		context: new Map([[CLE_LECTEUR, lecteur]])
	}).body;

/** Les lecteurs pleins hors lecture : un lien vers le MP3, que le lecteur du site intercepte. */
const lecteursPleins = (html: string) => html.match(/<a class="bouton ecouter[^"]*" href="\/audio\//g) ?? [];

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
		// Le seul autre lien est celui du lecteur, vers le relais audio du site.
		expect(html.match(/<a /g)).toHaveLength(2);
		expect(lecteursPleins(html)).toHaveLength(1);
	});

	it('rend chaque paragraphe du résumé et les deux listes', () => {
		const html = rendre(HOSTILE);
		expect(html.match(/<p>/g)?.length).toBe(2);
		expect(html).toContain('Second paragraphe.');
		expect(html).toContain('À lire');
		expect(html).toContain('À surveiller');
	});

	it("pose les lecteurs sur le relais audio du site, celui de la journée en mode global", () => {
		const parCategorie = rendre(HOSTILE, 'moi');
		expect(parCategorie).toContain('href="/audio/moi/2026-11-21/cyber.mp3"');
		expect(parCategorie).not.toContain('<audio');
		const globale = rendre(
			contenu({
				montage: { audio: 'journee.mp3', ecoute: '12 min' },
				categories: [{ ...HOSTILE.categories[0], audio: null }]
			})
		);
		expect(globale).toContain('href="/audio/moi/2026-11-21/journee.mp3"');
		expect(lecteursPleins(globale)).toHaveLength(1);
		expect(globale).not.toContain('<audio');
		expect(globale).toContain('12 min');
	});

	it('montre les commandes pleines, et non le lien, pour la piste en cours', () => {
		const element = {
			src: '',
			currentTime: 0,
			duration: Number.NaN,
			paused: true,
			play() {},
			pause() {},
			load() {},
			removeAttribute() {},
			addEventListener() {}
		};
		const lecteur = new LecteurAudio(() => element);
		lecteur.lancer(new PisteAudio('moi', '2026-11-21', 'cyber.mp3', 'x', false));
		const html = rendre(HOSTILE, 'moi', lecteur);
		expect(lecteursPleins(html)).toHaveLength(0);
		expect(html).toContain('type="range"');
		expect(html).toContain('aria-label="Lecture"');
	});

	it("affiche la raison d'une journée sans article, sans lecteur vide", () => {
		const html = rendre(contenu({ raison: 'Aucun article trouvé pour le vendredi 21 novembre 2026.' }));
		expect(html).toContain('Aucun article trouvé pour le vendredi 21 novembre 2026.');
		expect(html).not.toContain('<audio');
		expect(html).not.toContain('/audio/');
		expect(html).not.toContain('lecteur-plein');
		expect(html).not.toContain('<section');
	});

	it("annonce une journée en cours de production, sans la dire vide", () => {
		const html = rendre(contenu({ en_cours: true }));
		expect(html).toContain('en cours de production');
		expect(html).not.toContain('Aucun article');
	});
});
