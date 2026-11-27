/**
 * Le chargement des résumés par lots : dix journées par appel, le découpage est fait par
 * l'API (`decalage`/`limite` dans la query string), jamais filtré ni re-trié côté client.
 *
 * Partagé par la page des résumés (premier lot au rendu) et la route `lots` (lots suivants
 * au défilement) : mêmes données, mêmes indicateurs, pour que les cartes s'ajoutent à la
 * liste sans changer de rendu.
 */

import { ErreurApi, type ClientApiResume, type Journee, type LotJournees } from './api-resume.js';

import type { Utilisateur } from './comptes.js';

import { contexte } from './contexte.js';

/** La taille d'un lot de résumés. Constante : ce n'est pas un réglage. */
export const TAILLE_LOT = 10;

/** Ce qu'une carte de journée affiche en plus de sa date : durée, compteurs, bouton lecture. */
export interface IndicateursJournee {
	ecoute: string | null;
	categories: number;
	articles: number;
	montage: string | null;
	categoriesAudio: Record<string, string>;
}

/** Un lot de résumés chargé, prêt à être rendu seul ou ajouté à la liste. */
export interface LotResumes {
	journees: Journee[];
	indicateursJournees: Record<string, IndicateursJournee>;
	total: number;
	/** Vrai quand l'API a encore des journées au-delà de ce lot. */
	aSuite: boolean;
}

/** Charge le lot qui commence à `decalage`, avec les indicateurs de chacune de ses journées.
 *
 * Le tri date décroissante est entretenu par l'API ; retrié ici pour que la page n'en
 * dépende pas. Un profil que l'API ne connaît pas rend une liste vide quand c'est celui de
 * la personne connectée (son compte existe, l'API ne l'a pas encore vu) ; pour celui d'un
 * autre, l'erreur `introuvable` est relancée, que l'appelant rend en 404 pour ne pas
 * confirmer que ce nom existe.
 */
export async function chargerLotResumes(
	utilisateur: Utilisateur,
	username: string,
	decalage: number
): Promise<LotResumes> {
	const ctx = contexte();
	let lot: LotJournees;
	try {
		lot = await ctx.api.listerJournees(username, { decalage, limite: TAILLE_LOT });
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		if (cause.introuvable && username === utilisateur.username) {
			return { journees: [], indicateursJournees: {}, total: 0, aSuite: false };
		}
		throw cause;
	}
	const journees = [...lot.journees].sort((a, b) => b.date.localeCompare(a.date));
	return {
		journees,
		indicateursJournees: await _indicateurs(ctx.api, username, journees),
		total: lot.total,
		aSuite: decalage + journees.length < lot.total
	};
}

/** `montage` et `categoriesAudio` disent ce que joue le bouton de la carte : la journée
 * entière seulement si son fichier est le montage, sinon la catégorie dont il est l'audio.
 * Une journée dont le détail ne répond pas affiche des zéros plutôt que de faire échouer
 * tout le lot. */
async function _indicateurs(
	api: ClientApiResume,
	username: string,
	journees: Journee[]
): Promise<Record<string, IndicateursJournee>> {
	const indicateursJournees: Record<string, IndicateursJournee> = {};
	if (!journees.length) return indicateursJournees;
	const details = await Promise.all(
		journees.map(async (journee) => {
			try {
				const detail = await api.lireJournee(username, journee.date);
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
	return indicateursJournees;
}
