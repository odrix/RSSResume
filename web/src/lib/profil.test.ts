import { describe, expect, it } from 'vitest';
import { depuisLignes, lireFormulaireProfil, versLignes } from './profil.js';

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
