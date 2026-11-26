import { error } from '@sveltejs/kit';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import type { RequestHandler } from './$types';

/** La fin de l'écoute, signalée par le lecteur. Un POST à part et non le GET de l'audio :
 * celui-ci part aussi pour les métadonnées et chaque plage lue, et ne dit pas qu'on a écouté.
 *
 * Un seul 404 pour la journée absente et la journée d'un autre, comme sur ses pages. */
export const POST: RequestHandler = async ({ locals, params }) => {
	const utilisateur = locals.utilisateur;
	if (!utilisateur) error(401, 'Connexion requise');
	const ctx = contexte();
	// Propriété et format d'abord, sans l'API : c'est ce qui permet de marquer quand même si
	// elle ne répond pas.
	if (!ctx.journeesLues.peutMarquer(utilisateur, params.username, params.date)) {
		error(404, 'Journée introuvable');
	}
	try {
		if (!(await ctx.consultation.journee(utilisateur, params.username, params.date))) {
			error(404, 'Journée introuvable');
		}
	} catch (cause) {
		// Une API en panne ne doit pas faire perdre une écoute : seul « introuvable », rendu
		// `null` ci-dessus, refuse. Au pire, une ligne pour une journée qui n'existe pas, que
		// la liste n'affichera jamais.
		if (!(cause instanceof ErreurApi)) throw cause;
	}
	ctx.journeesLues.marquer(utilisateur, params.username, params.date, 'audio');
	return new Response(null, { status: 204 });
};
