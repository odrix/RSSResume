import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { REGIMES, type CategoriesProposees, type Profil, type ProfilSaisi } from '#lib/profil.js';
import { monter } from '#lib/server/outils-test.js';
import Page from './+page.svelte';

const PROFIL: Profil = {
	id: '3f2b8c1e-7d4a-4e9b-a0c5-1b2d3e4f5a6b',
	username: 'moi',
	profil: 'Développeuse back-end.',
	stack: [],
	email: ['moi@example.com'],
	prenom: '',
	securite: 'exploitant',
	modifie_le: '2026-11-23T07:00:00+00:00'
};

const CATEGORIES: CategoriesProposees = {
	ouvert: false,
	categories: [
		{ libelle: 'Tech', description: "L'actualité technique.", privee: false },
		{ libelle: 'Qualité', description: 'Tests et outillage.', privee: false },
		{ libelle: 'Veille concurrentielle', description: 'Les mouvements des concurrents.', privee: true }
	]
};

function rendre(data: Record<string, unknown>, form: unknown = null): string {
	const props = {
		data: {
			profil: PROFIL,
			depart: PROFIL,
			gabaritApplique: null,
			erreur: null,
			enAttente: [],
			categories: CATEGORIES,
			gabarits: [],
			...data
		},
		form
	};
	// La page n'attend que `data` et `form` ; le reste des props de SvelteKit n'y sert pas.
	// Les marqueurs d'hydratation et les retours à la ligne du source sont retirés : les
	// assertions portent sur le texte lu, pas sur la mise en page du composant.
	return render(Page, { props } as unknown as Parameters<typeof render<typeof Page>>[1])
		.body.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\s+/g, ' ');
}

/** Les champs `<input>` du rendu dont le nom est `nom`. */
function champs(html: string, nom: string): string[] {
	return (html.match(/<input[^>]*>/g) ?? []).filter((balise) => balise.includes(`name="${nom}"`));
}

function cochees(html: string): string[] {
	return champs(html, 'categories')
		.filter((balise) => /\schecked(=""|\s|>|\/)/.test(balise))
		.map((balise) => /value="([^"]*)"/.exec(balise)![1]);
}

/** Le bloc `<fieldset>` qui contient `texte`. */
function bloc(html: string, texte: string): string {
	return (html.match(/<fieldset[\s\S]*?<\/fieldset>/g) ?? []).find((fieldset) => fieldset.includes(texte)) ?? '';
}

/** Les blocs `<dialog>…</dialog>` du rendu. */
function dialogs(html: string): string[] {
	return html.match(/<dialog[\s\S]*?<\/dialog>/g) ?? [];
}

/** Le bouton d'une popup, celui qui porte `titre`. */
function boutonPopup(html: string, titre: string): string {
	return (
		(html.match(/<button[^>]*type="button"[^>]*>[\s\S]*?<\/button>/g) ?? []).find((bouton) =>
			bouton.includes(titre)
		) ?? ''
	);
}

describe('page Mon profil', () => {
	it('ne propose que les catégories autorisées, avec leur description', async () => {
		const { api } = monter();
		const html = rendre({ categories: await api.listerCategories('moi') });
		const proposees = champs(html, 'categories').map((balise) => /value="([^"]*)"/.exec(balise)![1]);
		expect(proposees).toContain('Veille concurrentielle');
		expect(proposees).toContain('Cybersécurité');
		// La catégorie privée d'une autre personne n'arrive jamais jusqu'à la page.
		expect(html).not.toContain('Veille interne');
		expect(html).toContain('Les mouvements des concurrents.');
		expect(html).toContain('privée, montrée à vous seul');
	});

	it('coche les catégories suivies, et toutes quand le profil n’en déclare pas', () => {
		expect(cochees(rendre({ depart: { ...PROFIL, categories: ['Qualité'] } }))).toEqual(['Qualité']);
		// Tri naturel des libellés, le même que celui de la journée et de l'email.
		expect(cochees(rendre({}))).toEqual(['Qualité', 'Tech', 'Veille concurrentielle']);
		expect(rendre({})).toContain('vous suivrez aussi les catégories ajoutées plus tard');
	});

	it('dit que tout est suivi quand le catalogue est ouvert, sans rien à cocher', () => {
		const html = rendre({ categories: { ouvert: true, categories: [] } });
		expect(champs(html, 'categories')).toEqual([]);
		expect(champs(html, 'categories_editees')).toEqual([]);
		expect(html).toContain('toutes les catégories sont suivies');
	});

	it("affiche l'erreur de validation sous le champ concerné", () => {
		const message = 'moi : catégorie « Veille interne » inconnue du catalogue.';
		const saisie: ProfilSaisi = { ...PROFIL, categories: ['Tech'] };
		const html = rendre({}, { message, saisie, champ: 'categories' });
		const categories = bloc(html, 'Catégories suivies');
		expect(categories).toContain(message);
		expect(champs(categories, 'categories').every((balise) => balise.includes('aria-invalid="true"'))).toBe(true);
		// Le bandeau en tête renvoie au champ sans répéter le message ; la saisie est conservée.
		expect(html.split(message)).toHaveLength(2);
		expect(cochees(html)).toEqual(['Tech']);

		const regime = rendre({}, { message: 'securite : refusé', saisie: PROFIL, champ: 'securite' });
		expect(bloc(regime, 'Régime de sécurité')).toContain('securite : refusé');
		expect(bloc(regime, 'Régime de sécurité')).toContain('aria-invalid="true"');
	});

	it('montre en tête une erreur dont le champ n’est pas sur la page', () => {
		const html = rendre({}, { message: 'flux_exclus : refusé', saisie: PROFIL, champ: 'flux_exclus' });
		expect(html).toMatch(/role="alert"[^>]*>\s*flux_exclus : refusé/);
	});

	it('présente la stack comme facultative, sans CERT-FR ni Keycloak', () => {
		const html = rendre({});
		expect(html).toContain('si vous exploitez des serveurs ou des logiciels');
		expect(html).toContain('ex. PostgreSQL');
		for (const interne of ['CERT-FR', 'Keycloak', 'RH-SSO']) expect(html).not.toContain(interne);
		// Repliée quand elle est vide, ouverte quand elle ne l'est pas.
		expect(html).not.toMatch(/<details[^>]*class="bloc stack[^"]*"[^>]*open/);
		expect(rendre({ depart: { ...PROFIL, stack: ['PostgreSQL'] } })).toMatch(/<details[^>]*open/);
	});

	it('explique chaque régime de sécurité en une ligne', () => {
		const html = rendre({ depart: { ...PROFIL, securite: 'decideur' } });
		expect(champs(html, 'securite')).toHaveLength(REGIMES.length);
		for (const regime of REGIMES) expect(html).toContain(regime.explication);
		const coche = champs(html, 'securite').filter((balise) => /\schecked/.test(balise));
		expect(coche).toHaveLength(1);
		expect(coche[0]).toContain('value="decideur"');
	});

	it("propose de repartir d'un gabarit, et dit que rien n'est enregistré", () => {
		const gabarits = [
			{ metier: 'qa', libelle: 'QA', profil: 'Testeuse.' },
			{ metier: 'rssi', libelle: 'RSSI', profil: 'RSSI.' }
		];
		const html = rendre({ gabarits, gabaritApplique: { metier: 'rssi', libelle: 'RSSI', categories: true } });
		expect(html).toContain('Repartir d');
		expect(html).toMatch(/<option value="rssi" selected/);
		expect(html).toContain('pré-rempli avec le gabarit « RSSI » : texte, régime, rubriques et catégories.');
		expect(html).toContain('Exemple : le gabarit « RSSI »');
		expect(html).toMatch(/<form method="POST" action="\/profil"/);
	});

	it('ne prétend pas appliquer les catégories du gabarit quand elles sont masquées', () => {
		const gabarits = [{ metier: 'rssi', libelle: 'RSSI', profil: 'RSSI.' }];
		const html = rendre({
			gabarits,
			categories: null,
			gabaritApplique: { metier: 'rssi', libelle: 'RSSI', categories: false }
		});
		expect(html).toContain('texte, régime et rubriques ; vos catégories ne changent pas.');
		expect(html).not.toContain('rubriques et catégories');
		expect(html).toContain('Remplace le texte, le régime de sécurité, les rubriques par ceux');
		expect(champs(html, 'categories_editees')).toEqual([]);
	});

	it('montre chaque section réglable en bouton résumant son état actuel', () => {
		const html = rendre({});
		expect(boutonPopup(html, 'Catégories suivies')).toContain('toutes suivies');
		expect(boutonPopup(html, 'Régime de sécurité')).toContain('Exploitant');
		expect(boutonPopup(html, 'Rubriques du résumé')).toContain('rubriques par défaut');
		expect(boutonPopup(html, 'Prénom')).toContain('non renseigné');
		expect(boutonPopup(html, 'Adresses de réception')).toContain('1 adresse');
		expect(boutonPopup(html, 'Stack surveillée')).toContain('aucune');

		const rempli = rendre({
			depart: {
				...PROFIL,
				categories: ['Qualité'],
				securite: 'decideur',
				axes: [{ slug: 'cyber', libelle: 'Cyber', description: 'Les failles.' }],
				prenom: 'Adrien',
				email: ['moi@example.com', 'autre@example.com'],
				stack: ['PostgreSQL']
			},
			enAttente: ['nouvelle@example.com']
		});
		expect(boutonPopup(rempli, 'Catégories suivies')).toContain('1 suivie');
		expect(boutonPopup(rempli, 'Régime de sécurité')).toContain('Décideur');
		expect(boutonPopup(rempli, 'Rubriques du résumé')).toContain('1 rubrique');
		expect(boutonPopup(rempli, 'Prénom')).toContain('Adrien');
		expect(boutonPopup(rempli, 'Adresses de réception')).toContain('3 adresses, dont 1 en attente');
		expect(boutonPopup(rempli, 'Stack surveillée')).toContain('1 logiciel');
	});

	it("met le contenu d'édition de chaque section dans un <dialog>, sauf le profil de veille", () => {
		const contenu = dialogs(rendre({}));
		// Six sections en popup : catégories, régime, rubriques, prénom, adresses, stack.
		expect(contenu).toHaveLength(6);
		const tout = contenu.join(' ');
		for (const nom of ['categories', 'securite', 'axe_libelle', 'prenom', 'email', 'stack_nom']) {
			expect(tout).toContain(`name="${nom}"`);
		}
		// La textarea « Profil de veille » reste sur la page, hors de tout dialog.
		expect(contenu.every((dialog) => !dialog.includes('name="profil"'))).toBe(true);
		expect(rendre({})).toContain('name="profil"');
		// Les dialogs sont fermés à l'affichage.
		expect(contenu.every((dialog) => !/<dialog[^>]*\sopen/.test(dialog))).toBe(true);
	});

	it('rend ouvert le dialog du champ refusé, et seulement celui-là', () => {
		const html = rendre({}, { message: 'securite : refusé', saisie: PROFIL, champ: 'securite' });
		const ouverts = dialogs(html).filter((dialog) => /<dialog[^>]*\sopen/.test(dialog));
		expect(ouverts).toHaveLength(1);
		expect(ouverts[0]).toContain('name="securite"');

		const refuse = rendre(
			{},
			{ message: 'catégorie inconnue', saisie: { ...PROFIL, categories: ['Tech'] }, champ: 'categories' }
		);
		const ouvert = dialogs(refuse).filter((dialog) => /<dialog[^>]*\sopen/.test(dialog));
		expect(ouvert).toHaveLength(1);
		expect(ouvert[0]).toContain('name="categories"');
	});
});
