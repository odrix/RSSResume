import { fail, redirect } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { poserCookieSession } from '#lib/server/cookie.js';
import { destinationApresConnexion, destinationSure } from '#lib/server/garde.js';
import { normaliserEmail } from '#lib/server/validation.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	if (locals.utilisateur) redirect(303, destinationSure(url.searchParams.get('suite')));
	return { confirme: url.searchParams.has('confirme'), reinitialise: url.searchParams.has('reinitialise') };
};

export const actions: Actions = {
	default: async ({ request, cookies, url, getClientAddress }) => {
		const donnees = await request.formData();
		const email = normaliserEmail(String(donnees.get('email') ?? ''));
		const motDePasse = String(donnees.get('motDePasse') ?? '');

		const ctx = contexte();
		const ip = getClientAddress();
		if (!ctx.limiteParEmail.autorise(email) || !ctx.limiteParIp.autorise(ip)) {
			const attente = Math.max(
				ctx.limiteParEmail.attenteSecondes(email),
				ctx.limiteParIp.attenteSecondes(ip)
			);
			return fail(429, {
				email,
				message: `Trop de tentatives. Réessayez dans ${Math.ceil(attente / 60)} minute(s).`
			});
		}

		// Plafonné pour qu'un mot de passe démesuré ne fasse pas travailler Argon2 pour rien.
		const utilisateur =
			email && motDePasse && motDePasse.length <= 1024
				? await ctx.comptes.authentifier(email, motDePasse)
				: null;
		if (!utilisateur) {
			ctx.limiteParEmail.noter(email);
			ctx.limiteParIp.noter(ip);
			// Un seul message pour l'adresse inconnue et le mauvais mot de passe.
			return fail(400, { email, message: 'Adresse ou mot de passe incorrect.' });
		}

		ctx.limiteParEmail.oublier(email);
		if (!utilisateur.confirme) {
			// Seul le titulaire du mot de passe voit ce message : il ne révèle rien à un tiers.
			return fail(403, {
				email,
				nonConfirme: true,
				message: "Votre adresse n'est pas encore confirmée. Ouvrez le lien reçu par email."
			});
		}
		const { jeton, expireLe } = ctx.sessions.ouvrir(utilisateur.id);
		poserCookieSession(cookies, jeton, expireLe);
		redirect(
			303,
			destinationApresConnexion(url.searchParams.get('suite'), () =>
				ctx.comptes.noterPremiereConnexion(utilisateur.id)
			)
		);
	}
};
