import { error } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { exigerConnexion } from '#lib/server/garde.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	// Un seul 404 pour l'absence et le refus : la page ne dit pas ce qui existe chez les autres.
	const contenu = await contexte().consultation.journee(utilisateur, params.username, params.date);
	if (!contenu) error(404, 'Journée introuvable');
	contexte().consultation.noter(utilisateur, params.date);
	return {
		username: params.username,
		proprietaire: params.username === utilisateur.username,
		contenu
	};
};
