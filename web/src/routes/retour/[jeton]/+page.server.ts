import { fail } from '@sveltejs/kit';
import { estAvis } from '#lib/retour.js';
import { contexte } from '#lib/server/contexte.js';
import { ErreurRetour, LIEN_RETOUR_INVALIDE, saisieRetour } from '#lib/server/retours.js';
import type { Actions, PageServerLoad } from './$types';

/* Ni `exigerConnexion`, ni session : qui reçoit la lettre n'a pas forcément de compte, et le
 * jeton signé du lien est la seule autorisation. Contrairement au désabonnement, aucun POST
 * d'ailleurs n'est attendu ici, le vote part du formulaire de cette page, et la route
 * garde donc la protection CSRF de toutes les autres. */

/** Afficher la page ne vote pas : un antivirus de messagerie qui ouvre le lien ne doit pas
 * voter à la place de la personne. L'avis du lien cliqué n'est qu'un pré-cochage ; à
 * défaut, celui du vote déjà donné. */
export const load: PageServerLoad = async ({ params, url }) => {
	const demande = url.searchParams.get('avis');
	try {
		const lecture = await contexte().retours.lireLien(params.jeton);
		if (!lecture) return { lecture: null, avis: null, invalide: LIEN_RETOUR_INVALIDE };
		return {
			lecture,
			avis: estAvis(demande) ? demande : (lecture.retour?.avis ?? null),
			invalide: null
		};
	} catch (erreur) {
		if (erreur instanceof ErreurRetour) return { lecture: null, avis: null, invalide: erreur.message };
		throw erreur;
	}
};

export const actions: Actions = {
	/** Le vote. Refusé, il rend le commentaire saisi : un texte écrit ne se perd pas sur une erreur. */
	default: async ({ params, request }) => {
		const form = await request.formData();
		const commentaire = String(form.get('commentaire') ?? '');
		const avis = form.get('avis');
		try {
			const lecture = await contexte().retours.voterParLien(params.jeton, saisieRetour(form));
			return { vote: lecture };
		} catch (erreur) {
			if (erreur instanceof ErreurRetour) {
				return fail(400, { message: erreur.message, commentaire, avis: estAvis(avis) ? avis : null });
			}
			throw erreur;
		}
	}
};
