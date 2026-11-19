import { error } from '@sveltejs/kit';
import { ErreurApi, type Journee } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { exigerConnexion } from '#lib/server/garde.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	// 404 et non 403 : la page ne confirme pas l'existence d'un username à qui n'y a pas droit.
	if (!utilisateur.peutConsulter(params.username)) error(404, 'Page introuvable');

	let journees: Journee[] = [];
	let erreur: string | null = null;
	try {
		journees = await contexte().api.listerJournees(params.username);
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		if (cause.introuvable && params.username !== utilisateur.username) error(404, 'Profil introuvable');
		erreur = cause.introuvable ? null : cause.message;
	}
	// L'API les rend déjà ainsi ; retrié ici pour que la page n'en dépende pas.
	journees.sort((a, b) => b.date.localeCompare(a.date));
	return {
		username: params.username,
		proprietaire: params.username === utilisateur.username,
		journees,
		erreur
	};
};
