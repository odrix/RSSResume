import { error } from '@sveltejs/kit';

import { ErreurApi, type Journee } from '#lib/server/api-resume.js';

import { contexte } from '#lib/server/contexte.js';

import { exigerConnexion } from '#lib/server/garde.js';

import { chargerLotResumes, type IndicateursJournee } from '#lib/server/lots-resumes.js';

import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	// 404 et non 403 : la page ne confirme pas l'existence d'un username à qui n'y a pas droit.
	if (!utilisateur.peutConsulter(params.username)) error(404, 'Page introuvable');

	// Un seul lot au rendu (les 10 plus récentes) : les suivants partent à la route `lots`,
	// au défilement. `lues` reste l'ensemble complet, pour marquer aussi les lots chargés après.
	let journees: Journee[] = [];
	let indicateursJournees: Record<string, IndicateursJournee> = {};
	let total = 0;
	let aSuite = false;
	let erreur: string | null = null;

	try {
		const lot = await chargerLotResumes(utilisateur, params.username, 0);
		({ journees, indicateursJournees, total, aSuite } = lot);
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		// `chargerLotResumes` a déjà répondu liste vide pour un 404 sur son propre profil :
		// un 404 qui arrive ici est celui du profil d'un autre.
		if (cause.introuvable) error(404, 'Profil introuvable');
		erreur = cause.message;
	}
	// Demandé seulement quand il sert : dire à qui n'a encore rien quand arrive son premier résumé.
	const passage = !erreur && total === 0 ? await contexte().consultation.passage() : null;
	return {
		username: params.username,
		proprietaire: params.username === utilisateur.username,
		journees,
		indicateursJournees,
		total,
		aSuite,
		// Un tableau et non le Set : ce qui part vers la page doit se sérialiser.
		lues: [...contexte().journeesLues.lues(utilisateur, params.username)],
		passage,
		erreur
	};
};
