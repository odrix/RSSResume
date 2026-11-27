import { error, json } from '@sveltejs/kit';

import { ErreurApi } from '#lib/server/api-resume.js';

import { exigerConnexion } from '#lib/server/garde.js';

import { chargerLotResumes } from '#lib/server/lots-resumes.js';

import type { RequestHandler } from './$types';

/** Le lot suivant de la liste des résumés, en JSON : la page vient le chercher à
 * l'approche du bas de page, avec `?decalage=N` — le nombre de journées déjà affichées.
 *
 * Mêmes gardes que la page : connexion exigée, consultation réservée au propriétaire et à
 * l'administrateur, et un 404 qui ne confirme pas l'existence d'un username à qui n'y a
 * pas droit.
 */
export const GET: RequestHandler = async ({ locals, url, params }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	if (!utilisateur.peutConsulter(params.username)) error(404, 'Page introuvable');

	const brut = url.searchParams.get('decalage') ?? '0';
	if (!/^\d+$/.test(brut)) error(400, 'decalage : un entier positif est attendu.');
	const decalage = Number(brut);

	try {
		const lot = await chargerLotResumes(utilisateur, params.username, decalage);
		return json({
			journees: lot.journees,
			indicateursJournees: lot.indicateursJournees,
			total: lot.total,
			aSuite: lot.aSuite
		});
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		if (cause.introuvable) error(404, 'Profil introuvable');
		// Statut 0 : l'API ne répond pas, un 502 dit au navigateur que le service est en panne.
		error(cause.statut >= 400 && cause.statut < 600 ? cause.statut : 502, cause.message);
	}
};
