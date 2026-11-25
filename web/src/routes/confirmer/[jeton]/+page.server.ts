import { fail, redirect } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { ErreurConfirmation, LIEN_INVALIDE, type JetonLu } from '#lib/server/jetons-email.js';
import type { Actions, PageServerLoad } from './$types';

/** Un lien de réinitialisation a sa propre page : ici, il ne confirme rien. */
function lireConfirmation(jeton: string): JetonLu | null {
	const lu = contexte().jetons.lire(jeton);
	return lu?.objet === 'reinitialisation' ? null : lu;
}

/** Afficher la page ne confirme rien : un antivirus de messagerie qui ouvre le lien ne doit
 * pas le consommer. Seul le bouton (POST, protégé du CSRF) confirme. */
export const load: PageServerLoad = ({ params }) => {
	const lu = lireConfirmation(params.jeton);
	return lu ? { objet: lu.objet, email: lu.email, invalide: null } : { objet: null, email: null, invalide: LIEN_INVALIDE };
};

export const actions: Actions = {
	default: async ({ params, url }) => {
		const ctx = contexte();
		const lu = lireConfirmation(params.jeton);
		try {
			if (lu?.objet === 'destinataire') {
				const { email } = await ctx.destinataires.confirmer(params.jeton);
				return { confirme: `${email} recevra désormais le résumé quotidien.` };
			}
			if (lu?.objet === 'adresse') {
				const { nouvelle } = await ctx.identifiants.confirmerAdresse(params.jeton);
				return { confirme: `Votre compte se connecte désormais avec ${nouvelle}.` };
			}
			await ctx.inscription.confirmer(params.jeton, url.origin);
		} catch (erreur) {
			if (erreur instanceof ErreurConfirmation) return fail(400, { message: erreur.message });
			throw erreur;
		}
		redirect(303, '/connexion?confirme=1');
	}
};
