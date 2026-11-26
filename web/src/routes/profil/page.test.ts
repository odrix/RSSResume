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

/** Le bloc repliable `<details>` qui contient `texte`. */
function section(html: string, texte: string): string {
	return (html.match(/<details[\s\S]*?<\/details>/g) ?? []).find((details) => details.includes(texte)) ?? '';
}

/** Le bloc `<fieldset>` qui contient `texte`. */
function bloc(html: string, texte: string): string {
	return (html.match(/<fieldset[\s\S]*?<\/fieldset>/g) ?? []).find((fieldset) => fieldset.includes(texte)) ?? '';
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
		const categories = section(html, 'Catégories suivies');
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
		// Les adresses de réception ne sont plus sur la page : leur erreur reste en tête.
		const email = rendre({}, { message: 'email : refusé', saisie: PROFIL, champ: 'email' });
		expect(email).toMatch(/role="alert"[^>]*>\s*email : refusé/);
	});

	it('met le prénom en haut du formulaire, toujours visible', () => {
		const html = rendre({ depart: { ...PROFIL, prenom: 'Adrien' } });
		const prenom = html.indexOf('name="prenom"');
		expect(prenom).toBeGreaterThan(-1);
		expect(prenom).toBeLessThan(html.indexOf('name="profil"'));
		expect(champs(html, 'prenom')[0]).toContain('value="Adrien"');
	});

	it('garde le régime de sécurité visible, juste après le profil de veille', () => {
		const html = rendre({});
		const profil = html.indexOf('name="profil"');
		const securite = html.indexOf('name="securite"');
		expect(profil).toBeGreaterThan(-1);
		expect(securite).toBeGreaterThan(profil);
		// Toujours visible : pas dans un bloc repliable.
		expect(bloc(html, 'Régime de sécurité')).not.toHaveLength(0);
		expect(section(html, 'Régime de sécurité')).toHaveLength(0);
		// Et avant les trois sections repliables.
		expect(securite).toBeLessThan(html.indexOf('Catégories suivies'));
	});

	it('explique chaque régime de sécurité en une ligne', () => {
		const html = rendre({ depart: { ...PROFIL, securite: 'decideur' } });
		expect(champs(html, 'securite')).toHaveLength(REGIMES.length);
		for (const regime of REGIMES) expect(html).toContain(regime.explication);
		const coche = champs(html, 'securite').filter((balise) => /\schecked/.test(balise));
		expect(coche).toHaveLength(1);
		expect(coche[0]).toContain('value="decideur"');
	});

	it('cache les adresses de réception, resoumises telles quelles pour être conservées', () => {
		const html = rendre({ enAttente: ['nouvelle@example.com'] });
		// Pas de champ visible : pas de textarea, un seul input caché.
		expect(html).not.toContain('<textarea name="email"');
		const email = champs(html, 'email');
		expect(email).toHaveLength(1);
		expect(email[0]).toContain('type="hidden"');
		expect(email[0]).toContain('moi@example.com');
		expect(email[0]).toContain('nouvelle@example.com');
	});

	it('replie par défaut les catégories, les rubriques et la stack', () => {
		const html = rendre({ depart: { ...PROFIL, categories: ['Tech'], stack: ['PostgreSQL'] } });
		for (const titre of ['Catégories suivies', 'Rubriques du résumé', 'Stack surveillée']) {
			const blocRepliable = section(html, titre);
			expect(blocRepliable).not.toHaveLength(0);
			expect(blocRepliable).not.toMatch(/<details[^>]*\sopen/);
		}
		// Un refus rouvre seulement la section concernée.
		const refuse = rendre({}, { message: 'stack : refusé', saisie: PROFIL, champ: 'stack' });
		expect(section(refuse, 'Stack surveillée')).toMatch(/<details[^>]*\sopen/);
		expect(section(refuse, 'Catégories suivies')).not.toMatch(/<details[^>]*\sopen/);
		expect(section(refuse, 'Rubriques du résumé')).not.toMatch(/<details[^>]*\sopen/);
	});

	it('présente la stack comme facultative, sans CERT-FR ni Keycloak', () => {
		const html = rendre({});
		expect(html).toContain('si vous exploitez des serveurs ou des logiciels');
		expect(html).toContain('ex. PostgreSQL');
		for (const interne of ['CERT-FR', 'Keycloak', 'RH-SSO']) expect(html).not.toContain(interne);
	});

	it("propose de repartir d'un gabarit en dessous du bouton Enregistrer", () => {
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
		const enregistrer = html.indexOf('>Enregistrer</button>');
		expect(enregistrer).toBeGreaterThan(-1);
		expect(html.indexOf('Repartir d')).toBeGreaterThan(enregistrer);
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
});
