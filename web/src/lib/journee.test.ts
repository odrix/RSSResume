import { describe, expect, it } from 'vitest';
import { paragraphes, urlSure } from './journee.js';

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
