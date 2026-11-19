import { describe, expect, it } from 'vitest';
import { PROFIL_PAR_DEFAUT } from '#lib/profil.js';
import { AlerteInscription } from './alerte.js';
import { ClientApiResume } from './api-resume.js';
import { ErreurInscription, Inscription, type SaisieInscription } from './inscription.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';

const SAISIE: SaisieInscription = {
	email: 'Moi@Example.com',
	username: 'moi',
	motDePasse: 'une phrase de passe',
	prenom: ' Adrien ',
	profil: ''
};

function alerteEspionne() {
	const envois: Request[] = [];
	const alerte = new AlerteInscription({
		cleApi: 're_test',
		expediteur: 'site@example.com',
		destinataire: EMAIL_ADMIN,
		fetch: async (entree, init) => {
			envois.push(new Request(entree, init));
			return new Response('{}', { status: 200 });
		}
	});
	return { alerte, envois };
}

async function echec(promesse: Promise<unknown>): Promise<ErreurInscription> {
	try {
		await promesse;
	} catch (erreur) {
		if (erreur instanceof ErreurInscription) return erreur;
		throw erreur;
	}
	throw new Error("l'inscription n'a pas échoué");
}

describe('Inscription', () => {
	it("crée le compte, le profil par défaut, et alerte l'administrateur", async () => {
		const { comptes, api, fausseApi } = monter();
		const { alerte, envois } = alerteEspionne();
		const utilisateur = await new Inscription(comptes, api, alerte).inscrire(SAISIE);

		expect(utilisateur.email).toBe('moi@example.com');
		expect(fausseApi.profils.get('moi')).toMatchObject({
			profil: PROFIL_PAR_DEFAUT,
			stack: [],
			email: ['moi@example.com'],
			prenom: 'Adrien'
		});
		expect(envois).toHaveLength(1);
		const corps = await envois[0].json();
		expect(corps.to).toEqual([EMAIL_ADMIN]);
		expect(corps.subject).toContain('moi');
	});

	it('garde le texte de profil saisi', async () => {
		const { comptes, api, fausseApi } = monter();
		await new Inscription(comptes, api, alerteEspionne().alerte).inscrire({ ...SAISIE, profil: 'RSSI' });
		expect(fausseApi.profils.get('moi')?.profil).toBe('RSSI');
	});

	it.each([
		[{ email: 'pas-une-adresse' }, 'email'],
		[{ username: 'Moi' }, 'username'],
		[{ motDePasse: 'court' }, 'motDePasse']
	] as const)("refuse une saisie invalide sans appeler l'API (%o)", async (changement, champ) => {
		const { comptes, api, fausseApi } = monter();
		const erreur = await echec(
			new Inscription(comptes, api, alerteEspionne().alerte).inscrire({ ...SAISIE, ...changement })
		);
		expect(erreur.champ).toBe(champ);
		expect(fausseApi.requetes).toHaveLength(0);
	});

	it("refuse un username pris côté API, sans créer de compte ni alerter", async () => {
		const { comptes, api } = monter();
		await api.creerProfil('moi', { profil: 'déjà là', stack: [], email: [], prenom: '' });
		const { alerte, envois } = alerteEspionne();
		const erreur = await echec(new Inscription(comptes, api, alerte).inscrire(SAISIE));
		expect(erreur.champ).toBe('username');
		expect(comptes.lister()).toHaveLength(0);
		expect(envois).toHaveLength(0);
	});

	it("refuse une adresse déjà inscrite avant d'appeler l'API", async () => {
		const { comptes, api, fausseApi } = monter();
		await comptes.creer('moi@example.com', 'ancien', 'une phrase de passe');
		const erreur = await echec(new Inscription(comptes, api, alerteEspionne().alerte).inscrire(SAISIE));
		expect(erreur.champ).toBe('email');
		expect(fausseApi.requetes).toHaveLength(0);
	});

	it("ne crée rien quand l'API est injoignable", async () => {
		const { comptes } = monter();
		const enPanne = new ClientApiResume({
			baseUrl: 'http://api.test',
			jeton: 'x',
			fetch: () => Promise.reject(new TypeError('fetch failed'))
		});
		const erreur = await echec(new Inscription(comptes, enPanne, alerteEspionne().alerte).inscrire(SAISIE));
		expect(erreur.champ).toBe('general');
		expect(comptes.lister()).toHaveLength(0);
	});

	it('supprime le profil créé si le compte ne peut pas l’être', async () => {
		const { comptes, api, fausseApi } = monter();
		// Une course : le compte apparaît entre la vérification et l'insertion.
		const creer = comptes.creer.bind(comptes);
		comptes.creer = async (email, username, motDePasse) => {
			await creer(email, username, motDePasse);
			return creer(email, username, motDePasse);
		};
		const erreur = await echec(new Inscription(comptes, api, alerteEspionne().alerte).inscrire(SAISIE));
		expect(erreur.champ).toBe('username');
		expect(fausseApi.profils.has('moi')).toBe(false);
	});

	it("n'échoue pas quand l'alerte n'est pas configurée", async () => {
		const { comptes, api } = monter();
		const sansCle = new AlerteInscription({ cleApi: '', expediteur: '', destinataire: EMAIL_ADMIN });
		const utilisateur = await new Inscription(comptes, api, sansCle).inscrire(SAISIE);
		expect(utilisateur.username).toBe('moi');
	});
});
