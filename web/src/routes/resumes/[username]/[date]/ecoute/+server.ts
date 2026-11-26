import { error } from '@sveltejs/kit';
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
	if (!(await ctx.consultation.journee(utilisateur, params.username, params.date))) {
		error(404, 'Journée introuvable');
	}
	if (!ctx.journeesLues.marquer(utilisateur, params.username, params.date, 'audio')) {
		error(404, 'Journée introuvable');
	}
	return new Response(null, { status: 204 });
};
