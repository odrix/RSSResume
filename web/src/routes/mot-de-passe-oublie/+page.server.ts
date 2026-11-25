import { fail } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { normaliserEmail } from '#lib/server/validation.js';
import type { Actions } from './$types';

/** La même réponse que l'adresse ait un compte ou non : la page ne sert pas à savoir qui
 * est inscrit. */
const REPONSE_OUBLI =
	"Si un compte existe pour cette adresse, un lien pour choisir un nouveau mot de passe vient de lui être envoyé. Il est valable une heure et remplace les précédents.";

export const actions: Actions = {
	default: async ({ request, url, getClientAddress }) => {
		const email = normaliserEmail(String((await request.formData()).get('email') ?? ''));
		const ctx = contexte();
		const ip = getClientAddress();
		if (!ctx.limiteOublisParEmail.autorise(email) || !ctx.limiteOublisParIp.autorise(ip)) {
			return fail(429, { email, message: 'Trop de demandes. Réessayez dans une heure.' });
		}
		ctx.limiteOublisParEmail.noter(email);
		ctx.limiteOublisParIp.noter(ip);
		if (email) ctx.reinitialisation.demander(email, url.origin);
		return { email, envoye: REPONSE_OUBLI };
	}
};
