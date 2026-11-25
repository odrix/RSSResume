import { render } from 'svelte/server';
import { describe, expect, it, vi } from 'vitest';
import Page from './+page.svelte';

const etat = vi.hoisted(() => ({ contact: 'contact@example.test' }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat }));

const { load } = await import('./+page.server.js');

function rendre(data: Record<string, unknown>): string {
	return render(Page, { props: { data, form: null } } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

describe('/confidentialite', () => {
	it('se lit sans être connecté, et dit comment demander la suppression du compte', async () => {
		const url = new URL('https://site.test/confidentialite');
		const data = await load({ locals: { utilisateur: null }, url } as never);

		expect(data).toEqual({ contact: 'contact@example.test' });
		const html = rendre(data as Record<string, unknown>);
		expect(html).toContain('La suppression de votre compte');
		expect(html).toContain('se demande au contact');
		expect(html).toContain('href="mailto:contact@example.test"');
		for (const sujet of ['Les données conservées', 'Finalité', 'Durée de conservation', 'Sous-traitants', 'Resend']) {
			expect(html).toContain(sujet);
		}
	});

	it("ne publie pas d'adresse quand aucune n'est configurée", () => {
		const html = rendre({ contact: '' });
		expect(html).not.toContain('mailto:');
		expect(html).toContain("pas encore publié d'adresse de contact");
	});
});
