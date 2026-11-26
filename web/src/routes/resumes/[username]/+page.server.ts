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
	/** `montage` et `categoriesAudio` disent ce que joue le bouton de la carte : la journée entière
	 * seulement si son fichier est le montage, sinon la catégorie dont il est l'audio. */
	const indicateursJournees: Record<
		string,
		{
			ecoute: string | null;
			categories: number;
			articles: number;
			montage: string | null;
			categoriesAudio: Record<string, string>;
		}
	> = {};
	if (!erreur && journees.length) {
		const details = await Promise.all(
			journees.map(async (journee) => {
				try {
					const detail = await contexte().api.lireJournee(params.username, journee.date);
					const totaux = detail.categories.reduce(
						(cumul, categorie) => {
							const articles = categorie.articles.length + categorie.a_surveiller.length;
							return {
								categories: cumul.categories + (articles > 0 ? 1 : 0),
								articles: cumul.articles + articles
							};
						},
						{ categories: 0, articles: 0 }
					);
					const categoriesAudio: Record<string, string> = {};
					for (const categorie of detail.categories) {
						if (categorie.audio) categoriesAudio[categorie.audio] = categorie.categorie;
					}
					return {
						date: journee.date,
						ecoute: detail.ecoute ?? detail.montage?.ecoute ?? null,
						...totaux,
						montage: detail.montage?.audio ?? null,
						categoriesAudio
					};
				} catch (cause) {
					if (!(cause instanceof ErreurApi)) throw cause;
					return { date: journee.date, ecoute: null, categories: 0, articles: 0, montage: null, categoriesAudio: {} };
				}
			})
		);
		for (const detail of details) {
			indicateursJournees[detail.date] = {
				ecoute: detail.ecoute,
				categories: detail.categories,
				articles: detail.articles,
				montage: detail.montage,
				categoriesAudio: detail.categoriesAudio
			};
		}
	}
	// Demandé seulement quand il sert : dire à qui n'a encore rien quand arrive son premier résumé.
	const passage = !erreur && !journees.length ? await contexte().consultation.passage() : null;
	return {
		username: params.username,
		proprietaire: params.username === utilisateur.username,
		journees,
		indicateursJournees,
		// Un tableau et non le Set : ce qui part vers la page doit se sérialiser.
		lues: [...contexte().journeesLues.lues(utilisateur, params.username)],
		passage,
		erreur
	};
};
