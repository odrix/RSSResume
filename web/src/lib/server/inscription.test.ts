import { describe, expect, it } from 'vitest';
import { PROFIL_PAR_DEFAUT } from '#lib/profil.js';
import { ClientApiResume } from './api-resume.js';
import { CourrierAbsent, CourrierJournal } from './courrier.js';
import { Inscription, ErreurInscription, type SaisieInscription } from './inscription.js';
import { DUREE_JETON_EMAIL_MS, ErreurConfirmation } from './jetons-email.js';
import { EMAIL_ADMIN, ORIGINE, jetonDuLien, monter } from './outils-test.js';

const SAISIE: SaisieInscription = {
	email: 'Moi@Example.com',
	username: 'moi',
	motDePasse: 'une phrase de passe',
	prenom: ' Adrien ',
	profil: ''
};

async function echec<E extends Error>(promesse: Promise<unknown>, type: new (...a: never[]) => E): Promise<E> {
	try {
		await promesse;
	} catch (erreur) {
		expect(erreur).toBeInstanceOf(type);
		return erreur as E;
	}
	throw new Error("l'appel n'a pas échoué");
}

describe('Inscription', () => {
	it("crée un compte en attente et envoie le lien, sans profil ni alerte", async () => {
		const { inscription, comptes, courrier, fausseApi } = monter();
		const utilisateur = await inscription.inscrire(SAISIE, ORIGINE);

		expect(utilisateur.confirme).toBe(false);
		expect(comptes.lister()).toHaveLength(1);
		expect(fausseApi.requetes).toHaveLength(0);
		expect(courrier.envoyes).toHaveLength(1);
		const [lien] = courrier.envoyes;
		expect(lien.destinataire).toBe('moi@example.com');
		expect(lien.texte).toContain(`${ORIGINE}/confirmer/`);
		expect(jetonDuLien(lien.texte)).toMatch(/^[A-Za-z0-9_-]{43}$/);
	});

	it('à la confirmation, crée le profil, confirme le compte et alerte l’administrateur', async () => {
		const { inscription, comptes, courrier, fausseApi } = monter();
		await inscription.inscrire(SAISIE, ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);

		const confirme = await inscription.confirmer(jeton);
		expect(confirme.confirme).toBe(true);
		expect(fausseApi.profils.get('moi')).toMatchObject({
			profil: PROFIL_PAR_DEFAUT,
			stack: [],
			email: ['moi@example.com'],
			prenom: 'Adrien'
		});
		expect(comptes.brouillon(confirme.id)).toEqual({ profil: '', prenom: '' });
		const alerte = courrier.envoyes.at(-1)!;
		expect(alerte.destinataire).toBe(EMAIL_ADMIN);
		expect(alerte.sujet).toContain('moi');

		// Usage unique.
		await echec(inscription.confirmer(jeton), ErreurConfirmation);
	});

	it('garde le texte de profil saisi jusqu’à la confirmation', async () => {
		const { inscription, courrier, fausseApi } = monter();
		await inscription.inscrire({ ...SAISIE, profil: 'RSSI' }, ORIGINE);
		await inscription.confirmer(jetonDuLien(courrier.envoyes[0].texte));
		expect(fausseApi.profils.get('moi')?.profil).toBe('RSSI');
	});

	it('refuse un lien expiré au bout de 24 heures', async () => {
		const h = { t: 1_800_000_000_000 };
		const { inscription, courrier, fausseApi } = monter(() => h.t);
		await inscription.inscrire(SAISIE, ORIGINE);
		h.t += DUREE_JETON_EMAIL_MS;
		await echec(inscription.confirmer(jetonDuLien(courrier.envoyes[0].texte)), ErreurConfirmation);
		expect(fausseApi.profils.size).toBe(0);
	});

	it('refuse un jeton inconnu, ou celui d’un destinataire', async () => {
		const { inscription, jetons, creerConfirme } = monter();
		await echec(inscription.confirmer('inconnu'), ErreurConfirmation);
		const moi = await creerConfirme('moi@example.com', 'moi');
		const autreObjet = jetons.emettre(moi.id, 'moi@example.com', 'destinataire');
		await echec(inscription.confirmer(autreObjet), ErreurConfirmation);
	});

	it('garde le lien utilisable quand l’API est indisponible', async () => {
		const { comptes, jetons, courrier, inscription, fausseApi } = monter();
		await inscription.inscrire(SAISIE, ORIGINE);
		const jeton = jetonDuLien(courrier.envoyes[0].texte);
		const enPanne = new ClientApiResume({
			baseUrl: 'http://api.test',
			jeton: 'x',
			fetch: () => Promise.reject(new TypeError('fetch failed'))
		});
		await echec(new Inscription(comptes, jetons, enPanne, courrier).confirmer(jeton), ErreurConfirmation);
		expect(comptes.lister()[0].confirme).toBe(false);

		await inscription.confirmer(jeton);
		expect(fausseApi.profils.has('moi')).toBe(true);
	});

	it('ne confirme pas quand le username est déjà pris côté API', async () => {
		const { inscription, api, courrier, comptes } = monter();
		await api.creerProfil('moi', { profil: 'déjà là', stack: [], email: [], prenom: '' });
		await inscription.inscrire(SAISIE, ORIGINE);
		const erreur = await echec(
			inscription.confirmer(jetonDuLien(courrier.envoyes[0].texte)),
			ErreurConfirmation
		);
		expect(erreur.message).toMatch(/déjà utilisé/);
		expect(comptes.lister()[0].confirme).toBe(false);
	});

	it.each([
		[{ email: 'pas-une-adresse' }, 'email'],
		[{ username: 'Moi' }, 'username'],
		[{ motDePasse: 'court' }, 'motDePasse']
	] as const)('refuse une saisie invalide sans rien créer (%o)', async (changement, champ) => {
		const { inscription, comptes, courrier } = monter();
		const erreur = await echec(inscription.inscrire({ ...SAISIE, ...changement }, ORIGINE), ErreurInscription);
		expect(erreur.champ).toBe(champ);
		expect(comptes.lister()).toHaveLength(0);
		expect(courrier.envoyes).toHaveLength(0);
	});

	it('refuse une adresse ou un username déjà réservés, même en attente', async () => {
		const { inscription } = monter();
		await inscription.inscrire(SAISIE, ORIGINE);
		expect((await echec(inscription.inscrire({ ...SAISIE, username: 'autre' }, ORIGINE), ErreurInscription)).champ).toBe(
			'email'
		);
		expect(
			(await echec(inscription.inscrire({ ...SAISIE, email: 'autre@example.com' }, ORIGINE), ErreurInscription))
				.champ
		).toBe('username');
	});

	it("libère l'adresse d'un compte abandonné depuis sept jours", async () => {
		const h = { t: 1_800_000_000_000 };
		const { inscription, comptes } = monter(() => h.t);
		await inscription.inscrire(SAISIE, ORIGINE);
		h.t += 7 * 24 * 60 * 60 * 1000 + 1;
		await inscription.inscrire({ ...SAISIE, username: 'nouveau' }, ORIGINE);
		expect(comptes.lister().map((c) => c.username)).toEqual(['nouveau']);
	});

	it('refuse l’inscription en production sans transport d’email', async () => {
		const { comptes, jetons, api } = monter();
		const fermee = new Inscription(comptes, jetons, api, new CourrierAbsent(EMAIL_ADMIN));
		const erreur = await echec(fermee.inscrire(SAISIE, ORIGINE), ErreurInscription);
		expect(erreur.champ).toBe('general');
		expect(erreur.message).toMatch(/fermées/);
		expect(comptes.lister()).toHaveLength(0);
	});

	it("supprime le compte quand le lien n'a pas pu partir", async () => {
		const { comptes, jetons, api } = monter();
		class CourrierEnPanne extends CourrierJournal {
			protected override async transmettre(): Promise<boolean> {
				return false;
			}
		}
		const inscription = new Inscription(comptes, jetons, api, new CourrierEnPanne(EMAIL_ADMIN, false));
		const erreur = await echec(inscription.inscrire(SAISIE, ORIGINE), ErreurInscription);
		expect(erreur.champ).toBe('general');
		expect(comptes.lister()).toHaveLength(0);
	});

	it('renvoie un nouveau lien à un compte en attente, et rien aux autres', async () => {
		const { inscription, courrier, creerConfirme } = monter();
		await inscription.inscrire(SAISIE, ORIGINE);
		const premier = jetonDuLien(courrier.envoyes[0].texte);
		await inscription.renvoyer('MOI@example.com', ORIGINE);
		expect(courrier.envoyes).toHaveLength(2);
		const second = jetonDuLien(courrier.envoyes[1].texte);

		// Seul le dernier lien fonctionne.
		await echec(inscription.confirmer(premier), ErreurConfirmation);
		await inscription.confirmer(second);

		await creerConfirme('autre@example.com', 'autre');
		const avant = courrier.envoyes.length;
		await inscription.renvoyer('autre@example.com', ORIGINE);
		await inscription.renvoyer('inconnu@example.com', ORIGINE);
		await inscription.renvoyer('moi@example.com', ORIGINE);
		expect(courrier.envoyes).toHaveLength(avant);
	});
});
