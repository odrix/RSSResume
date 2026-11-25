/**
 * Ce que les tests partagent : une base en mémoire, un hacheur instantané, la fausse API,
 * un courrier qui garde ses messages. Jamais importé par le site.
 */

import { FausseApi } from '../../../mock/faux-api.js';
import { ClientApiResume } from './api-resume.js';
import { ouvrirBase } from './base.js';
import { Comptes, HacheurMotDePasse, type Utilisateur } from './comptes.js';
import { CourrierJournal } from './courrier.js';
import { Desabonnement } from './desabonnement.js';
import { Destinataires } from './destinataires.js';
import { Identifiants } from './identifiants.js';
import { Inscription } from './inscription.js';
import { JetonsEmail } from './jetons-email.js';
import { LimiteurTentatives } from './limiteur.js';
import { MagicLink } from './magic-link.js';
import { Reinitialisation } from './reinitialisation.js';
import { Retours } from './retours.js';
import { Sessions } from './sessions.js';

export const JETON = 'jeton-de-test';
export const EMAIL_ADMIN = 'admin@example.test';
export const ORIGINE = 'https://site.test';

/** Argon2 coûte quelques dizaines de millisecondes par appel : inutile hors de son test. */
export class FauxHacheur extends HacheurMotDePasse {
	override async hacher(motDePasse: string): Promise<string> {
		return `faux:${motDePasse}`;
	}

	override async verifier(empreinte: string, motDePasse: string): Promise<boolean> {
		return empreinte === `faux:${motDePasse}`;
	}
}

/** Le jeton d'un lien envoyé — confirmation ou réinitialisation —, relu dans le texte du message. */
export function jetonDuLien(texte: string): string {
	const trouve = /\/(?:confirmer|reinitialiser)\/([A-Za-z0-9_-]+)/.exec(texte);
	if (!trouve) throw new Error(`pas de lien dans : ${texte}`);
	return trouve[1];
}

/** Laisse partir ce qui a été différé par `setImmediate` — le lien du mot de passe oublié. */
export function envoisDifferes(): Promise<void> {
	return new Promise((resoudre) => setImmediate(resoudre));
}

export function monter(maintenant: () => number = Date.now) {
	const base = ouvrirBase(':memory:');
	const comptes = new Comptes(base, EMAIL_ADMIN, new FauxHacheur(), maintenant);
	const sessions = new Sessions(base, comptes, maintenant);
	const jetons = new JetonsEmail(base, maintenant);
	const courrier = new CourrierJournal(EMAIL_ADMIN, false);
	const fausseApi = new FausseApi(JETON);
	const api = new ClientApiResume({
		baseUrl: 'http://api.test/',
		jeton: JETON,
		fetch: fausseApi.traiter
	});
	const inscription = new Inscription(comptes, jetons, api, courrier);
	const destinataires = new Destinataires(
		base,
		comptes,
		jetons,
		api,
		courrier,
		new LimiteurTentatives(10, 60 * 60 * 1000, maintenant)
	);
	const desabonnement = new Desabonnement(api);
	const retours = new Retours(api);
	const reinitialisation = new Reinitialisation(comptes, jetons, sessions, courrier);
	const identifiants = new Identifiants(comptes, jetons, sessions, courrier);
	const magicLink = new MagicLink(comptes, jetons, courrier, base, maintenant);

	/** Un compte confirmé, sans passer par l'API : pour les tests qui ne portent pas sur
	 * l'inscription. */
	async function creerConfirme(email: string, username: string): Promise<Utilisateur> {
		const cree = await comptes.creer(email, username, 'une phrase de passe');
		comptes.confirmer(cree.id);
		return comptes.parId(cree.id)!;
	}

	return {
		base,
		comptes,
		sessions,
		jetons,
		courrier,
		fausseApi,
		api,
		inscription,
		destinataires,
		desabonnement,
		retours,
		reinitialisation,
		identifiants,
		magicLink,
		creerConfirme
	};
}
