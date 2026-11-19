import { fail } from '@sveltejs/kit';
import { lireFormulaireProfil, type Profil } from '#lib/profil.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { ErreurDestinataire } from '#lib/server/destinataires.js';
import { exigerConnexion } from '#lib/server/garde.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	const ctx = contexte();
	let profil: Profil | null = null;
	let erreur: string | null = null;
	try {
		profil = await ctx.api.lireProfil(utilisateur.username);
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		erreur = cause.introuvable
			? "Votre profil n'existe pas encore côté service de résumé : l'enregistrer le créera."
			: cause.message;
	}
	return { profil, erreur, enAttente: ctx.destinataires.enAttente(utilisateur.id) };
};

export const actions: Actions = {
	default: async ({ locals, request, url }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const saisie = lireFormulaireProfil(await request.formData());
		try {
			const { liensEnvoyes } = await contexte().destinataires.enregistrerProfil(
				utilisateur,
				saisie,
				url.origin
			);
			return { enregistre: true, liensEnvoyes };
		} catch (erreur) {
			if (erreur instanceof ErreurDestinataire) return fail(422, { message: erreur.message, saisie });
			if (!(erreur instanceof ErreurApi)) throw erreur;
			// 422 : la validation de l'API, affichée telle quelle avec la saisie conservée.
			return fail(erreur.statut === 422 ? 422 : 502, { message: erreur.message, saisie });
		}
	}
};
