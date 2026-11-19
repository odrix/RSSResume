import { fail } from '@sveltejs/kit';
import { lireFormulaireProfil, type Profil } from '#lib/profil.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { exigerConnexion } from '#lib/server/garde.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	let profil: Profil | null = null;
	let erreur: string | null = null;
	try {
		profil = await contexte().api.lireProfil(utilisateur.username);
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		erreur = cause.introuvable
			? "Votre profil n'existe pas encore côté service de résumé : l'enregistrer le créera."
			: cause.message;
	}
	return { profil, erreur, bienvenue: url.searchParams.has('bienvenue') };
};

export const actions: Actions = {
	default: async ({ locals, request, url }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const saisie = lireFormulaireProfil(await request.formData());
		const api = contexte().api;
		try {
			try {
				await api.modifierProfil(utilisateur.username, saisie);
			} catch (erreur) {
				// Un compte dont le profil a disparu côté API le retrouve en l'enregistrant.
				if (!(erreur instanceof ErreurApi && erreur.introuvable)) throw erreur;
				await api.creerProfil(utilisateur.username, saisie);
			}
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			// 422 : la validation de l'API, affichée telle quelle avec la saisie conservée.
			return fail(erreur.statut === 422 ? 422 : 502, { message: erreur.message, saisie });
		}
		return { enregistre: true };
	}
};
