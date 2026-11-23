import { beforeEach, describe, expect, it } from 'vitest';
import type { ProfilSaisi } from '#lib/profil.js';
import { ErreurApi } from './api-resume.js';
import type { Utilisateur } from './comptes.js';
import { CourrierAbsent } from './courrier.js';
import { Destinataires, ErreurDestinataire, MAX_EN_ATTENTE } from './destinataires.js';
import { ErreurConfirmation } from './jetons-email.js';
import { LimiteurTentatives } from './limiteur.js';
import { EMAIL_ADMIN, ORIGINE, jetonDuLien, monter } from './outils-test.js';

const MOI = 'moi@example.com';

function saisie(email: string[]): ProfilSaisi {
	return { profil: 'CTO', stack: [], email, prenom: '', securite: 'exploitant' };
}

async function echec<E extends Error>(promesse: Promise<unknown>, type: new (...a: never[]) => E): Promise<E> {
	try {
		await promesse;
	} catch (erreur) {
		expect(erreur).toBeInstanceOf(type);
		return erreur as E;
	}
	throw new Error("l'appel n'a pas échoué");
}

describe('Destinataires', () => {
	let env: ReturnType<typeof monter>;
	let moi: Utilisateur;

	beforeEach(async () => {
		env = monter();
		moi = await env.creerConfirme(MOI, 'moi');
		await env.api.creerProfil('moi', saisie([MOI, 'ancien@example.com']));
	});

	const emailsApi = () => env.fausseApi.profils.get('moi')?.email;

	it("n'envoie pas à l'API une adresse ajoutée : elle attend son lien", async () => {
		const resultat = await env.destinataires.enregistrerProfil(
			moi,
			saisie([MOI, 'ancien@example.com', 'Nouveau@Example.com']),
			ORIGINE
		);
		expect(emailsApi()).toEqual([MOI, 'ancien@example.com']);
		expect(resultat.liensEnvoyes).toEqual(['nouveau@example.com']);
		expect(env.destinataires.enAttente(moi.id)).toEqual(['nouveau@example.com']);
		const lien = env.courrier.envoyes.at(-1)!;
		expect(lien.destinataire).toBe('nouveau@example.com');

		await env.destinataires.confirmer(jetonDuLien(lien.texte));
		expect(emailsApi()).toEqual([MOI, 'ancien@example.com', 'nouveau@example.com']);
		expect(env.destinataires.enAttente(moi.id)).toEqual([]);
		// Usage unique.
		await echec(env.destinataires.confirmer(jetonDuLien(lien.texte)), ErreurConfirmation);
	});

	it('retire une adresse immédiatement', async () => {
		await env.destinataires.enregistrerProfil(moi, saisie([MOI]), ORIGINE);
		expect(emailsApi()).toEqual([MOI]);
		expect(env.courrier.envoyes).toHaveLength(0);
	});

	it("rétablit sans lien l'adresse du compte, déjà prouvée à l'inscription", async () => {
		await env.destinataires.enregistrerProfil(moi, saisie([]), ORIGINE);
		await env.destinataires.enregistrerProfil(moi, saisie([MOI]), ORIGINE);
		expect(emailsApi()).toEqual([MOI]);
		expect(env.courrier.envoyes).toHaveLength(0);
	});

	it('garde une adresse en attente sans renvoyer de lien, et annule celle qu’on retire', async () => {
		await env.destinataires.enregistrerProfil(moi, saisie([MOI, 'a@example.com', 'b@example.com']), ORIGINE);
		expect(env.courrier.envoyes).toHaveLength(2);
		const lienB = env.courrier.envoyes.find((m) => m.destinataire === 'b@example.com')!;

		await env.destinataires.enregistrerProfil(moi, saisie([MOI, 'a@example.com']), ORIGINE);
		expect(env.courrier.envoyes).toHaveLength(2);
		expect(env.destinataires.enAttente(moi.id)).toEqual(['a@example.com']);
		// Le lien de l'adresse retirée ne la fait pas revenir.
		await echec(env.destinataires.confirmer(jetonDuLien(lienB.texte)), ErreurConfirmation);
		expect(emailsApi()).toEqual([MOI]);
	});

	it("refuse une adresse invalide sans appeler l'API", async () => {
		env.fausseApi.requetes.length = 0;
		await echec(env.destinataires.enregistrerProfil(moi, saisie(['pas-une-adresse']), ORIGINE), ErreurDestinataire);
		expect(env.fausseApi.requetes).toHaveLength(0);
	});

	it(`plafonne à ${MAX_EN_ATTENTE} adresses en attente`, async () => {
		const trop = Array.from({ length: MAX_EN_ATTENTE + 1 }, (_, i) => `n${i}@example.com`);
		await echec(env.destinataires.enregistrerProfil(moi, saisie(trop), ORIGINE), ErreurDestinataire);
		expect(env.destinataires.enAttente(moi.id)).toEqual([]);
	});

	it('limite la fréquence des liens envoyés', async () => {
		const destinataires = new Destinataires(
			env.base,
			env.comptes,
			env.jetons,
			env.api,
			env.courrier,
			new LimiteurTentatives(1, 60 * 60 * 1000)
		);
		await destinataires.enregistrerProfil(moi, saisie([MOI, 'a@example.com']), ORIGINE);
		const erreur = await echec(
			destinataires.enregistrerProfil(moi, saisie([MOI, 'a@example.com', 'b@example.com']), ORIGINE),
			ErreurDestinataire
		);
		expect(erreur.message).toMatch(/Trop/);
	});

	it("refuse d'ajouter une adresse sans transport d'email, mais laisse en retirer", async () => {
		const sansCourrier = new Destinataires(
			env.base,
			env.comptes,
			env.jetons,
			env.api,
			new CourrierAbsent(EMAIL_ADMIN),
			new LimiteurTentatives(10, 60 * 60 * 1000)
		);
		await echec(sansCourrier.enregistrerProfil(moi, saisie([MOI, 'n@example.com']), ORIGINE), ErreurDestinataire);
		await sansCourrier.enregistrerProfil(moi, saisie([MOI]), ORIGINE);
		expect(emailsApi()).toEqual([MOI]);
	});

	it("recrée le profil s'il a disparu côté API", async () => {
		env.fausseApi.profils.delete('moi');
		const { profil } = await env.destinataires.enregistrerProfil(moi, saisie([MOI]), ORIGINE);
		expect(profil.username).toBe('moi');
		expect(emailsApi()).toEqual([MOI]);
	});

	it('enregistrer Mon profil garde les axes et catégories du gabarit', async () => {
		const axes = [{ slug: 'menaces', libelle: 'Menaces', description: 'campagnes actives' }];
		env.fausseApi.profils.delete('moi');
		await env.api.creerProfil('moi', { ...saisie([MOI]), axes, categories: ['Cybersécurité'] });

		// Le formulaire ne porte ni axes ni catégories.
		await env.destinataires.enregistrerProfil(moi, { ...saisie([MOI, 'autre@example.com']), profil: 'RSSI' }, ORIGINE);
		expect(env.fausseApi.profils.get('moi')).toMatchObject({ profil: 'RSSI', axes, categories: ['Cybersécurité'] });

		// Confirmer une adresse réécrit aussi le profil entier : rien ne doit s'y perdre.
		await env.destinataires.confirmer(jetonDuLien(env.courrier.envoyes.at(-1)!.texte));
		expect(env.fausseApi.profils.get('moi')).toMatchObject({
			email: [MOI, 'autre@example.com'],
			axes,
			categories: ['Cybersécurité']
		});
	});

	it('enregistre les catégories cochées dans la clé categories, et les axes saisis', async () => {
		const axes = [
			{ slug: 'tests', libelle: 'Tests', description: 'outillage' },
			{ slug: 'qualite', libelle: 'Qualité', description: 'revue de code' },
			{ slug: 'livraison', libelle: 'Livraison', description: 'déploiement' }
		];
		await env.destinataires.enregistrerProfil(
			moi,
			{ ...saisie([MOI]), axes, categories: ['Tech generaliste', 'Veille concurrentielle'] },
			ORIGINE
		);
		expect(env.fausseApi.profils.get('moi')).toMatchObject({
			axes,
			categories: ['Tech generaliste', 'Veille concurrentielle']
		});
	});

	it('tout coché : la clé categories disparaît, et une liste d’axes vide revient au défaut', async () => {
		const axes = [{ slug: 'menaces', libelle: 'Menaces', description: 'campagnes actives' }];
		env.fausseApi.profils.delete('moi');
		await env.api.creerProfil('moi', { ...saisie([MOI]), axes, categories: ['Cybersécurité'] });

		await env.destinataires.enregistrerProfil(moi, { ...saisie([MOI]), axes: [], categories: null }, ORIGINE);
		const profil = env.fausseApi.profils.get('moi');
		expect(profil).not.toHaveProperty('categories');
		expect(profil).not.toHaveProperty('axes');
		const corps = await env.fausseApi.requetes.at(-1)!.json();
		expect(corps).not.toHaveProperty('categories');
	});

	it("rattache au champ des adresses le refus d'une adresse", async () => {
		const erreur = await echec(
			env.destinataires.enregistrerProfil(moi, saisie(['pas-une-adresse']), ORIGINE),
			ErreurDestinataire
		);
		expect(erreur.champ).toBe('email');
	});

	it("refuse une catégorie privée d'un autre, et le dit sur le champ", async () => {
		const erreur = await echec(
			env.destinataires.enregistrerProfil(moi, { ...saisie([MOI]), categories: ['Veille interne'] }, ORIGINE),
			ErreurApi
		);
		expect(erreur.statut).toBe(422);
		expect(erreur.champ).toBe('categories');
	});

	it("refuse un jeton d'inscription ou inconnu", async () => {
		await echec(env.destinataires.confirmer('inconnu'), ErreurConfirmation);
		const jeton = env.jetons.emettre(moi.id, MOI, 'inscription');
		await echec(env.destinataires.confirmer(jeton), ErreurConfirmation);
	});
});
