import { describe, expect, it } from 'vitest';
import {
	categoriesTriees,
	paragraphes,
	triNaturel,
	urlSure,
	type ContenuJournee
} from './journee.js';

describe('urlSure', () => {
	it('urlSure ne garde que http(s)', () => {
		for (const url of ['https://exemple.test/a', 'http://exemple.test/b?c=d#e', 'HTTPS://Exemple.test/']) {
			expect(urlSure(url)).toBe(url);
		}
		expect(urlSure('  https://exemple.test/a \n')).toBe('https://exemple.test/a');
		for (const url of [
			'javascript:alert(1)',
			' JaVaScRiPt:alert(1)',
			'java\tscript:alert(1)',
			'data:text/html,<script>alert(1)</script>',
			'vbscript:msgbox',
			'//hote/chemin',
			'ftp://exemple.test/fichier',
			'https:///sans-hote',
			'http:exemple.test',
			'/relatif',
			'',
			null,
			undefined
		]) {
			expect(urlSure(url), String(url)).toBeNull();
		}
	});
});

describe('paragraphes', () => {
	it('coupe un résumé sur ses lignes vides, comme l’email', () => {
		expect(paragraphes('Premier.\n\nSecond,\nsuite.\n \nTroisième.\n\n\n')).toEqual([
			'Premier.',
			'Second,\nsuite.',
			'Troisième.'
		]);
		expect(paragraphes('')).toEqual([]);
		expect(paragraphes('  \n\n ')).toEqual([]);
	});
});

describe('triNaturel', () => {
	it('trie le préfixe numérique comme un nombre : « 2 » avant « 11 »', () => {
		expect(['11 - Veille', '2 - Alertes', '1 - Annonces'].sort(triNaturel)).toEqual([
			'1 - Annonces',
			'2 - Alertes',
			'11 - Veille'
		]);
	});

	it('classe les libellés sans préfixe après, par ordre alphabétique', () => {
		expect(['Cybersécurité', '2 - Alertes', 'veille', 'Marché'].sort(triNaturel)).toEqual([
			'2 - Alertes',
			'Cybersécurité',
			'Marché',
			'veille'
		]);
	});

	it('départage au texte quand le numéro est le même', () => {
		expect(triNaturel('2 - Alpha', '2 - bêta')).toBeLessThan(0);
	});
});

describe('categoriesTriees', () => {
	it('rend les catégories de la journée dans le même ordre que l’email', () => {
		const categorie = (nom: string): ContenuJournee['categories'][number] => ({
			categorie: nom,
			racontee: true,
			resume: '',
			audio: null,
			ecoute: null,
			articles: [],
			a_surveiller: []
		});
		const contenu = {
			categories: [categorie('11 - Veille'), categorie('Cybersécurité'), categorie('2 - Alertes')]
		} as ContenuJournee;

		expect(categoriesTriees(contenu).map((c) => c.categorie)).toEqual([
			'2 - Alertes',
			'11 - Veille',
			'Cybersécurité'
		]);
		// Le contenu d'origine n'est pas modifié.
		expect(contenu.categories[0].categorie).toBe('11 - Veille');
	});
});
