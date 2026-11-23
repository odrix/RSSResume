import { fail } from '@sveltejs/kit';
import {
	categoriesACocher,
	depuisGabarit,
	erreurSaisieProfil,
	lireFormulaireProfil,
	saisieAReafficher,
	type CategoriesProposees,
	type Gabarit,
	type Profil,
	type ProfilSaisi
} from '#lib/profil.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { ErreurDestinataire } from '#lib/server/destinataires.js';
import { exigerConnexion } from '#lib/server/garde.js';
import type { Actions, PageServerLoad } from './$types';

/** Une lecture dont l'échec ne doit coûter que sa section : la page reste utilisable pour
 * écrire son texte même si le catalogue ou les gabarits sont injoignables. Seule une
 * `ErreurApi` est rattrapée, une autre exception est un défaut du site. */
async function auMieux<T>(lecture: Promise<T>, defaut: T): Promise<T> {
	try {
		return await lecture;
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		return defaut;
	}
}

/** Le profil, ou la phrase qui dit pourquoi il manque. */
async function lireProfil(username: string): Promise<{ profil: Profil | null; erreur: string | null }> {
	try {
		return { profil: await contexte().api.lireProfil(username), erreur: null };
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		const erreur = cause.introuvable
			? "Votre profil n'existe pas encore côté service de résumé : l'enregistrer le créera."
			: cause.message;
		return { profil: null, erreur };
	}
}

export const load: PageServerLoad = async ({ locals, url }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	const ctx = contexte();
	const [{ profil, erreur }, categories, gabarits] = await Promise.all([
		lireProfil(utilisateur.username),
		auMieux<CategoriesProposees | null>(ctx.api.listerCategories(utilisateur.username), null),
		auMieux<Gabarit[]>(ctx.api.listerGabarits(), [])
	]);

	// « Repartir d'un gabarit » : un simple GET, qui pré-remplit sans rien enregistrer.
	const gabarit = gabarits.find((candidat) => candidat.metier === url.searchParams.get('gabarit'));
	const depart: ProfilSaisi | null = gabarit ? depuisGabarit(profil, gabarit, categories) : profil;
	return {
		profil,
		depart,
		// `categories` dit si celles du gabarit ont été reprises : sans catégories à cocher,
		// le bandeau ne doit pas prétendre les avoir appliquées.
		gabaritApplique: gabarit
			? {
					metier: gabarit.metier,
					libelle: gabarit.libelle,
					categories: categoriesACocher(categories).length > 0
				}
			: null,
		erreur,
		enAttente: ctx.destinataires.enAttente(utilisateur.id),
		categories,
		gabarits: gabarits.map(({ metier, libelle, profil: texte }) => ({ metier, libelle, profil: texte }))
	};
};

export const actions: Actions = {
	default: async ({ locals, request, url }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const donnees = await request.formData();
		const saisie = lireFormulaireProfil(donnees);
		// Ce que la page réaffiche après un refus : la saisie, sans les slugs fabriqués.
		const refusee = (statut: number, message: string, champ: string | null) =>
			fail(statut, { message, saisie: saisieAReafficher(saisie, donnees), champ });
		const refus = erreurSaisieProfil(saisie);
		if (refus) return refusee(422, refus.message, refus.champ);
		try {
			const { liensEnvoyes } = await contexte().destinataires.enregistrerProfil(
				utilisateur,
				saisie,
				url.origin
			);
			return { enregistre: true, liensEnvoyes };
		} catch (erreur) {
			if (erreur instanceof ErreurDestinataire) return refusee(422, erreur.message, erreur.champ);
			if (!(erreur instanceof ErreurApi)) throw erreur;
			// 422 : la validation de l'API, affichée sous le champ qu'elle nomme, la saisie conservée.
			const invalide = erreur.statut === 422;
			return refusee(invalide ? 422 : 502, erreur.message, invalide ? erreur.champ : null);
		}
	}
};
