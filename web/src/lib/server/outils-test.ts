/**
 * Ce que les tests partagent : une base en mémoire, un hacheur instantané, la fausse API.
 * Jamais importé par le site.
 */

import { FausseApi } from '../../../mock/faux-api.js';
import { ClientApiResume } from './api-resume.js';
import { ouvrirBase } from './base.js';
import { Comptes, HacheurMotDePasse } from './comptes.js';
import { Sessions } from './sessions.js';

export const JETON = 'jeton-de-test';
export const EMAIL_ADMIN = 'admin@example.test';

/** Argon2 coûte quelques dizaines de millisecondes par appel : inutile hors de son test. */
export class FauxHacheur extends HacheurMotDePasse {
	override async hacher(motDePasse: string): Promise<string> {
		return `faux:${motDePasse}`;
	}

	override async verifier(empreinte: string, motDePasse: string): Promise<boolean> {
		return empreinte === `faux:${motDePasse}`;
	}
}

export function monter(maintenant: () => number = Date.now) {
	const base = ouvrirBase(':memory:');
	const comptes = new Comptes(base, EMAIL_ADMIN, new FauxHacheur());
	const sessions = new Sessions(base, comptes, maintenant);
	const fausseApi = new FausseApi(JETON);
	const api = new ClientApiResume({
		baseUrl: 'http://api.test/',
		jeton: JETON,
		fetch: fausseApi.traiter
	});
	return { base, comptes, sessions, fausseApi, api };
}
