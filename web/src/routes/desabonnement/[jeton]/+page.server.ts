import { fail } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { ErreurDesabonnement, LIEN_DESABONNEMENT_INVALIDE } from '#lib/server/desabonnement.js';
import type { Actions, PageServerLoad } from './$types';

/* Ni `exigerConnexion`, ni session, ni cookie : qui reçoit la lettre n'a pas forcément de
 * compte, et le jeton signé du lien est la seule autorisation. C'est aussi pourquoi
 * `hooks.server.ts` laisse passer les POST d'ailleurs vers cette route, et vers elle seule. */

/** Afficher la page ne désabonne pas, comme `/confirmer` ne confirme pas : un antivirus de
 * messagerie qui ouvre le lien ne doit pas couper la lettre à la place de la personne. */
export const load: PageServerLoad = async ({ params }) => {
	try {
		const demande = await contexte().desabonnement.lire(params.jeton);
		return demande
			? { demande, invalide: null }
			: { demande: null, invalide: LIEN_DESABONNEMENT_INVALIDE };
	} catch (erreur) {
		if (erreur instanceof ErreurDesabonnement) return { demande: null, invalide: erreur.message };
		throw erreur;
	}
};

/** Le bouton de la page, et le POST en un clic de Gmail ou Yahoo (`List-Unsubscribe-Post`).
 * Les deux arrivent ici ; le corps — `List-Unsubscribe=One-Click` pour le second — n'est
 * pas lu : il ne dit rien que l'URL ne dise déjà. */
export const actions: Actions = {
	default: async ({ params }) => {
		try {
			const { username } = await contexte().desabonnement.appliquer(params.jeton);
			return { desabonne: username };
		} catch (erreur) {
			if (erreur instanceof ErreurDesabonnement) return fail(400, { message: erreur.message });
			throw erreur;
		}
	}
};
