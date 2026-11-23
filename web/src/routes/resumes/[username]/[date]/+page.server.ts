import { error, fail } from '@sveltejs/kit';
import type { Retour } from '#lib/server/api-resume.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { exigerConnexion } from '#lib/server/garde.js';
import { ErreurRetour, saisieRetour } from '#lib/server/retours.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url, params }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	// Un seul 404 pour l'absence et le refus : la page ne dit pas ce qui existe chez les autres.
	const contenu = await contexte().consultation.journee(utilisateur, params.username, params.date);
	if (!contenu) error(404, 'Journée introuvable');
	contexte().consultation.noter(utilisateur, params.date);

	const proprietaire = params.username === utilisateur.username;
	// Le vote déjà donné, pour pré-remplir : sans lui, un second envoi effacerait en silence
	// le commentaire laissé depuis la lettre. Au mieux : une API muette n'empêche pas de lire.
	let retour: Retour | null = null;
	if (proprietaire) {
		try {
			retour = await contexte().retours.lire(utilisateur, params.username, params.date);
		} catch (cause) {
			if (!(cause instanceof ErreurApi)) throw cause;
		}
	}
	return { username: params.username, proprietaire, contenu, retour };
};

export const actions: Actions = {
	/** Le vote du propriétaire, sur une journée qu'il peut lire. Un administrateur qui consulte
	 * la journée d'un autre ne vote pas : le formulaire ne lui est pas montré, et l'envoi est
	 * refusé comme une journée introuvable. */
	default: async ({ locals, url, params, request }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const form = await request.formData();
		const commentaire = String(form.get('commentaire') ?? '');
		if (params.username !== utilisateur.username) error(404, 'Journée introuvable');
		const ctx = contexte();
		if (!(await ctx.consultation.journee(utilisateur, params.username, params.date))) {
			error(404, 'Journée introuvable');
		}
		try {
			const retour = await ctx.retours.voter(utilisateur, params.username, params.date, saisieRetour(form));
			if (!retour) error(404, 'Journée introuvable');
			return { vote: retour };
		} catch (erreur) {
			if (erreur instanceof ErreurRetour) return fail(400, { message: erreur.message, commentaire });
			throw erreur;
		}
	}
};
