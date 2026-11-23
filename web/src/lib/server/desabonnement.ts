/**
 * Le lien de désabonnement de la lettre quotidienne : le relayer à l'API, sans session.
 *
 * Le jeton est signé par le travailleur avec un secret que seuls lui et l'API connaissent ;
 * le site ne sait pas le vérifier et n'a pas à le savoir. Il le transmet, et rend ce que
 * l'API répond. Aucune connexion n'est demandée : qui reçoit la lettre n'a pas forcément de
 * compte, et Gmail comme Yahoo exigent un désabonnement qui n'en demande pas.
 */

import { ErreurApi, type ClientApiResume, type DemandeDesabonnement } from './api-resume.js';

export const LIEN_DESABONNEMENT_INVALIDE = 'Ce lien de désabonnement est invalide ou déjà utilisé.';

/** Un désabonnement qui n'a pas pu se faire, avec le message à montrer. */
export class ErreurDesabonnement extends Error {}

/** De quoi écarter sans appel ce qui ne peut pas être un jeton : les champs signés, séparés
 * par des points, dans l'alphabet d'URL — et une longueur bornée. */
const MOTIF_JETON = /^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$/;
/** Le jeton porte huit caractères par destinataire de la lettre, en plus d'environ 85 fixes,
 * et un profil n'a pas de plafond de destinataires : la borne laisse passer quelque
 * quatre cents adresses, et n'arrête que ce qui ne peut pas être un lien. */
const LONGUEUR_MAX_JETON = 4096;

function jetonPlausible(jeton: string): boolean {
	return jeton.length <= LONGUEUR_MAX_JETON && MOTIF_JETON.test(jeton);
}

export class Desabonnement {
	constructor(private readonly api: ClientApiResume) {}

	/** Ce que le lien désabonnerait, ou `null` s'il est invalide ou déjà servi.
	 *
	 * L'affichage de la page n'appelle que ceci : un antivirus de messagerie qui ouvre le
	 * lien ne doit pas désabonner à la place de la personne. */
	async lire(jeton: string): Promise<DemandeDesabonnement | null> {
		if (!jetonPlausible(jeton)) return null;
		try {
			return await this.api.lireDesabonnement(jeton);
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) return null;
			if (erreur instanceof ErreurApi) throw new ErreurDesabonnement(erreur.message);
			throw erreur;
		}
	}

	/** Vide les destinataires du profil. Un lien invalide ou déjà servi :
	 * `ErreurDesabonnement`, avec le même message dans les deux cas. */
	async appliquer(jeton: string): Promise<{ username: string }> {
		if (!jetonPlausible(jeton)) throw new ErreurDesabonnement(LIEN_DESABONNEMENT_INVALIDE);
		try {
			return await this.api.desabonner(jeton);
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) {
				throw new ErreurDesabonnement(LIEN_DESABONNEMENT_INVALIDE);
			}
			if (erreur instanceof ErreurApi) throw new ErreurDesabonnement(erreur.message);
			throw erreur;
		}
	}
}
