import { render } from 'svelte/server';

import { createRawSnippet } from 'svelte';
import { describe, expect, it } from 'vitest';

import Popup from './Popup.svelte';

/** Le contenu d'édition passé en slot : un simple paragraphe reconnaissable. */
const CONTENU = 'Contenu d’édition ici';

function rendre(props: { titre: string; resume: string; ouvert?: boolean }): string {
	// Les marqueurs d'hydratation et les retours à la ligne du source sont retirés : les
	// assertions portent sur le texte lu, pas sur la mise en page du composant.
	return render(Popup, {
		props: {
			...props,
			children: createRawSnippet(() => ({ render: () => `<p>${CONTENU}</p>` }))
		}
	})
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

describe('Popup', () => {
	it('rend un bouton avec le titre et le résumé, et le contenu du slot dans un <dialog> fermé', () => {
		const html = rendre({ titre: 'Régime de sécurité', resume: 'Exploitant' });
		expect(html).toMatch(/<button[^>]*type="button"[^>]*>[^<]*<strong>Régime de sécurité<\/strong>[^<]*<span[^>]*>Exploitant<\/span>/);
		const dialog = (html.match(/<dialog[\s\S]*?<\/dialog>/) ?? [''])[0];
		expect(dialog).toContain(CONTENU);
		expect(dialog).toMatch(/<button[^>]*type="button"[^>]*>Fermer<\/button>/);
		// Fermée par défaut : pas d'attribut `open`.
		expect(dialog).not.toMatch(/<dialog[^>]*\sopen/);
	});

	it('rend le <dialog> ouvert quand `ouvert` est vrai', () => {
		const html = rendre({ titre: 'Prénom', resume: 'non renseigné', ouvert: true });
		expect(html).toMatch(/<dialog[^>]*\sopen[^>]*>/);
		expect(html).toContain(CONTENU);
	});
});
