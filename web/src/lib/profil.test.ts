import { describe, expect, it } from 'vitest';
import { GABARITS_DEMO } from '../../mock/faux-api.js';
import {
	depuisGabarit,
	depuisLignes,
	depuisLignesAxes,
	erreurSaisieProfil,
	lireFormulaireProfil,
	slugAxe,
	versLignes,
	versLignesAxes,
	type ProfilSaisi
} from './profil.js';

/** Un formulaire qui montre les catégories et les axes, comme la page quand l'API les sert. */
function formulaireComplet(cochees: string[], axes: [string, string, string][]): FormData {
	const donnees = new FormData();
	donnees.set('profil', 'QA');
	donnees.set('categories_editees', '1');
	for (const libelle of ['Tech', 'Cybersécurité', 'Veille concurrentielle']) {
		donnees.append('categories_proposees', libelle);
	}
	for (const libelle of cochees) donnees.append('categories', libelle);
	donnees.set('axes_edites', '1');
	for (const [slug, libelle, description] of axes) {
		donnees.append('axe_slug', slug);
		donnees.append('axe_libelle', libelle);
		donnees.append('axe_description', description);
	}
	return donnees;
}

describe('catégories et axes du formulaire de profil', () => {
	it('relit les catégories cochées et les axes, en ignorant les lignes vides', () => {
		const saisie = lireFormulaireProfil(
			formulaireComplet(
				['Tech', 'Veille concurrentielle'],
				[
					['tests', ' Tests ', ' outillage, méthodes '],
					['', '', ''],
					['', 'Qualité', 'revue de code'],
					['', '  ', '  ']
				]
			)
		);
		expect(saisie.categories).toEqual(['Tech', 'Veille concurrentielle']);
		expect(saisie.axes).toEqual([
			{ slug: 'tests', libelle: 'Tests', description: 'outillage, méthodes' },
			{ slug: 'qualite', libelle: 'Qualité', description: 'revue de code' }
		]);
	});

	it("n'envoie ni axes ni catégories quand la page ne les a pas montrés", () => {
		const donnees = new FormData();
		donnees.set('profil', 'QA');
		// Sans marqueur, une case égarée ne suffit pas à réécrire l'abonnement.
		donnees.append('categories', 'Tech');
		const saisie = lireFormulaireProfil(donnees);
		expect(saisie).not.toHaveProperty('axes');
		expect(saisie).not.toHaveProperty('categories');
	});

	it('tout coché : la clé est retirée, pour suivre aussi les catégories futures', () => {
		const saisie = lireFormulaireProfil(formulaireComplet(['Tech', 'Cybersécurité', 'Veille concurrentielle'], []));
		expect(saisie.categories).toBeNull();
		expect(saisie.axes).toEqual([]);
		expect(erreurSaisieProfil(saisie)).toBeNull();
	});

	it('refuse aucune catégorie cochée, que l’API lirait comme « tout »', () => {
		const saisie = lireFormulaireProfil(formulaireComplet([], []));
		expect(saisie.categories).toEqual([]);
		expect(erreurSaisieProfil(saisie)).toMatchObject({ champ: 'categories' });
	});

	it('garde le slug d’un axe existant, même renommé, et en fabrique un distinct pour un nouveau', () => {
		expect(
			depuisLignesAxes([
				{ slug: 'qualite', libelle: 'Qualité logicielle', description: 'tests' },
				{ slug: '', libelle: 'Qualité', description: 'revue' },
				{ slug: '', libelle: 'Qualité', description: 'outillage' }
			]).map((axe) => axe.slug)
		).toEqual(['qualite', 'qualite-2', 'qualite-3']);
		for (const [libelle, attendu] of [
			['Sécurité & conformité', 'securite-conformite'],
			['5G', 'axe-5g'],
			['Q', 'axe-q'],
			['', 'axe'],
			['Une rubrique au nom vraiment très long', 'une-rubrique-au-nom-vrai']
		]) {
			const slug = slugAxe(libelle);
			expect(slug).toBe(attendu);
			// Le motif exact de `rssresume/axes.py`.
			expect(slug).toMatch(/^[a-z][a-z0-9-]{1,23}$/);
		}
		expect(slugAxe('Une rubrique au nom vraiment très long', ['une-rubrique-au-nom-vrai'])).toBe(
			'une-rubrique-au-nom-vr-2'
		);
	});

	it('complète les axes du profil par des lignes libres, jusqu’à six', () => {
		const lignes = versLignesAxes([{ slug: 'tests', libelle: 'Tests', description: 'outillage' }]);
		expect(lignes).toHaveLength(6);
		expect(lignes[0]).toEqual({ slug: 'tests', libelle: 'Tests', description: 'outillage' });
		expect(lignes[5]).toEqual({ slug: '', libelle: '', description: '' });
	});

	it('repartir d’un gabarit remplace texte, régime, axes et catégories, et garde le reste', () => {
		const actuel: ProfilSaisi = {
			profil: 'Mon texte',
			stack: ['PostgreSQL'],
			email: ['moi@example.com'],
			prenom: 'Camille',
			securite: 'curieux',
			axes: [{ slug: 'a', libelle: 'A', description: 'a' }],
			categories: ['Tech']
		};
		const rssi = GABARITS_DEMO.find((gabarit) => gabarit.metier === 'rssi')!;
		expect(depuisGabarit(actuel, rssi)).toEqual({
			profil: rssi.profil,
			stack: ['PostgreSQL'],
			email: ['moi@example.com'],
			prenom: 'Camille',
			securite: rssi.securite,
			axes: rssi.axes,
			categories: rssi.categories
		});
		expect(depuisGabarit(null, rssi)).toMatchObject({ stack: [], email: [], prenom: '', profil: rssi.profil });
	});
});

describe('formulaire de profil', () => {
	it('relit texte, prénom, adresses et stack', () => {
		const donnees = new FormData();
		donnees.set('profil', '  CTO d’un SaaS  ');
		donnees.set('prenom', ' Adrien ');
		donnees.set('email', 'a@example.com\nb@example.com, c@example.com;');
		donnees.set('securite', 'decideur');
		for (const [nom, alias] of [
			['Traefik', ''],
			['Keycloak', 'RH-SSO, Red Hat SSO'],
			['', 'ignoré sans nom']
		]) {
			donnees.append('stack_nom', nom);
			donnees.append('stack_alias', alias);
		}
		expect(lireFormulaireProfil(donnees)).toEqual({
			profil: 'CTO d’un SaaS',
			prenom: 'Adrien',
			email: ['a@example.com', 'b@example.com', 'c@example.com'],
			stack: ['Traefik', { nom: 'Keycloak', alias: ['RH-SSO', 'Red Hat SSO'] }],
			securite: 'decideur'
		});
	});

	it('rend des champs vides quand rien n’est saisi', () => {
		expect(lireFormulaireProfil(new FormData())).toEqual({
			profil: '',
			prenom: '',
			email: [],
			stack: [],
			securite: 'exploitant'
		});
	});

	it('fait l’aller-retour entre la stack et les lignes de l’éditeur', () => {
		const stack = ['Traefik', { nom: 'Keycloak', alias: ['RH-SSO'] }, { nom: 'Nginx' }];
		expect(versLignes(stack)).toEqual([
			{ nom: 'Traefik', alias: '' },
			{ nom: 'Keycloak', alias: 'RH-SSO' },
			{ nom: 'Nginx', alias: '' }
		]);
		expect(depuisLignes(versLignes(stack))).toEqual(['Traefik', { nom: 'Keycloak', alias: ['RH-SSO'] }, 'Nginx']);
	});
});
