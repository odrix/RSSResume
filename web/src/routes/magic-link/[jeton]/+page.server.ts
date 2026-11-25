import { fail, redirect } from '@sveltejs/kit';
import { ErreurConfirmation, LIEN_INVALIDE } from '#lib/server/jetons-email.js';
import { contexte } from '#lib/server/contexte.js';
import { poserCookieSession } from '#lib/server/cookie.js';
import { destinationApresConnexion } from '#lib/server/garde.js';
import type { Actions, PageServerLoad } from './$types';

/** Un jeton de magic-link doit avoir l'objet 'magic-link'. */
function lireMagicLink(jeton: string) {
	const lu = contexte().jetons.lire(jeton);
	return lu?.objet === 'magic-link' ? lu : null;
}

/** Afficher la page ne valide pas le jeton : un simple GET ne doit pas consommer le jeton. */
export const load: PageServerLoad = ({ params }) => {
	const lu = lireMagicLink(params.jeton);
	return lu ? { email: lu.email, invalide: null } : { email: null, invalide: LIEN_INVALIDE };
};

export const actions: Actions = {
	default: async ({ params, cookies, url }) => {
		const ctx = contexte();
		
		const utilisateur = ctx.magicLink.valider(params.jeton);
		if (!utilisateur) {
			return fail(400, { message: LIEN_INVALIDE });
		}

		// Créer la session
		const { jeton, expireLe } = ctx.sessions.ouvrir(utilisateur.id);
		poserCookieSession(cookies, jeton, expireLe);

		// Rediriger après connexion
		redirect(
			303,
			destinationApresConnexion(url.searchParams.get('suite'), () =>
				ctx.comptes.noterPremiereConnexion(utilisateur.id)
			)
		);
	}
};
