import { fail } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { ErreurMagicLink } from '#lib/server/magic-link.js';
import { normaliserEmail } from '#lib/server/validation.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals }) => {
	// Rediriger si déjà connecté
	if (locals.utilisateur) {
		return { dejaConnecte: true };
	}
	return { dejaConnecte: false };
};

export const actions: Actions = {
	default: async ({ request, getClientAddress, url }) => {
		const donnees = await request.formData();
		const email = normaliserEmail(String(donnees.get('email') ?? ''));

		const ctx = contexte();
		const ip = getClientAddress();
		const origine = url.origin;

		try {
			await ctx.magicLink.demander(email, origine, ip);
		} catch (erreur) {
			if (erreur instanceof ErreurMagicLink) {
				return fail(erreur.raison === 'limite' ? 429 : 503, {
					email,
					message: erreur.message
				});
			}
			throw erreur;
		}

		// Toujours dire que l'email a été envoyé (même pour un email inconnu)
		return { envoye: true, email };
	}
};
