import { fail } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { normaliserEmail } from '#lib/server/validation.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ url }) => {
	return { email: url.searchParams.get('email') ?? '' };
};

/** La même réponse que l'adresse ait un compte en attente, un compte confirmé ou aucun :
 * la page ne sert pas à savoir qui est inscrit. */
const REPONSE =
	"Si un compte en attente existe pour cette adresse, un nouveau lien vient de lui être envoyé. Il est valable 24 heures et remplace les précédents.";

export const actions: Actions = {
	default: async ({ request, url, getClientAddress }) => {
		const email = normaliserEmail(String((await request.formData()).get('email') ?? ''));
		const ctx = contexte();
		const ip = getClientAddress();
		if (!ctx.limiteRenvoisParEmail.autorise(email) || !ctx.limiteRenvoisParIp.autorise(ip)) {
			return fail(429, { email, message: 'Trop de demandes. Réessayez dans une heure.' });
		}
		ctx.limiteRenvoisParEmail.noter(email);
		ctx.limiteRenvoisParIp.noter(ip);
		if (email) await ctx.inscription.renvoyer(email, url.origin);
		return { email, envoye: REPONSE };
	}
};
