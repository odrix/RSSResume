import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Toutes les pages Svelte des routes, lues comme du texte. */
function pages(dossier: string): string[] {
	return readdirSync(dossier, { withFileTypes: true }).flatMap((entree) => {
		const chemin = join(dossier, entree.name);
		if (entree.isDirectory()) return pages(chemin);
		return entree.name.endsWith('.svelte') ? [chemin] : [];
	});
}

describe('politique de référent des pages', () => {
	/* Une page en `no-referrer` fait envoyer `Origin: null` à ses formulaires POST : la
	 * protection CSRF de SvelteKit les refuse alors tous (« Cross-site POST form submissions
	 * are forbidden »). C'est arrivé à la page de confirmation, en production. L'en-tête
	 * `Referrer-Policy: same-origin` de hooks.server.ts suffit à garder les jetons des URL
	 * hors des autres sites ; aucune page n'a à le durcir. */
	it("aucune page ne déclare de référent qui retire l'origine des formulaires", () => {
		const fautives = pages(join(import.meta.dirname))
			.filter((chemin) => /name=["']referrer["']/i.test(readFileSync(chemin, 'utf8')));
		expect(fautives).toEqual([]);
	});
});
