import { fail, redirect } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { ErreurConfirmation, LIEN_INVALIDE } from '#lib/server/jetons-email.js';
import type { Actions, PageServerLoad } from './$types';

/** Afficher la page ne confirme rien : un antivirus de messagerie qui ouvre le lien ne doit
 * pas le consommer. Seul le bouton (POST, protégé du CSRF) confirme. */
export const load: PageServerLoad = ({ params }) => {
	const lu = contexte().jetons.lire(params.jeton);
	return lu ? { objet: lu.objet, email: lu.email, invalide: null } : { objet: null, email: null, invalide: LIEN_INVALIDE };
};

export const actions: Actions = {
	default: async ({ params }) => {
		const ctx = contexte();
		const lu = ctx.jetons.lire(params.jeton);
		try {
			if (lu?.objet === 'destinataire') {
				const { email } = await ctx.destinataires.confirmer(params.jeton);
				return { confirme: `${email} recevra désormais le résumé quotidien.` };
			}
			await ctx.inscription.confirmer(params.jeton);
		} catch (erreur) {
			if (erreur instanceof ErreurConfirmation) return fail(400, { message: erreur.message });
			throw erreur;
		}
		redirect(303, '/connexion?confirme=1');
	}
};
