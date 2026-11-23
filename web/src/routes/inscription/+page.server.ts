import { fail, redirect } from '@sveltejs/kit';
import { PROFIL_PAR_DEFAUT } from '#lib/profil.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { ErreurInscription, type SaisieInscription } from '#lib/server/inscription.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.utilisateur) redirect(303, '/resumes');
	let gabarits: { metier: string; libelle: string; profil: string; categories: string[] }[] = [];
	let indisponible = false;
	try {
		// Seul ce que la page montre : axes et régime restent côté serveur, qui les relira
		// de l'API à l'envoi plutôt que de croire ce que le navigateur renverrait.
		gabarits = (await contexte().api.listerGabarits()).map(({ metier, libelle, profil, categories }) => ({
			metier,
			libelle,
			profil,
			categories
		}));
	} catch (erreur) {
		if (!(erreur instanceof ErreurApi)) throw erreur;
		// L'inscription reste ouverte : la personne décrit alors son métier, comme avant.
		indisponible = true;
	}
	const demande = url.searchParams.get('metier') ?? '';
	return {
		gabarits,
		indisponible,
		profilParDefaut: PROFIL_PAR_DEFAUT,
		metier: gabarits.some((gabarit) => gabarit.metier === demande) ? demande : ''
	};
};

export const actions: Actions = {
	default: async ({ request, url, getClientAddress }) => {
		const donnees = await request.formData();
		const saisie: SaisieInscription = {
			email: String(donnees.get('email') ?? ''),
			username: String(donnees.get('username') ?? '').trim(),
			motDePasse: String(donnees.get('motDePasse') ?? ''),
			prenom: String(donnees.get('prenom') ?? ''),
			profil: String(donnees.get('profil') ?? ''),
			metier: String(donnees.get('metier') ?? '').trim()
		};
		// Le mot de passe ne revient jamais dans la page, même en cas d'erreur.
		const valeurs = {
			email: saisie.email,
			username: saisie.username,
			prenom: saisie.prenom,
			profil: saisie.profil,
			metier: saisie.metier
		};

		const ctx = contexte();
		const ip = getClientAddress();
		if (!ctx.limiteInscriptions.autorise(ip)) {
			return fail(429, {
				champ: 'general',
				message: 'Trop de comptes créés depuis cette adresse. Réessayez dans une heure.',
				valeurs
			});
		}

		try {
			const utilisateur = await ctx.inscription.inscrire(saisie, url.origin);
			ctx.limiteInscriptions.noter(ip);
			// Pas de session : le compte ne s'ouvre qu'une fois l'adresse confirmée.
			return { envoye: utilisateur.email };
		} catch (erreur) {
			if (erreur instanceof ErreurInscription) {
				return fail(erreur.champ === 'general' ? 503 : 400, {
					champ: erreur.champ,
					message: erreur.message,
					valeurs
				});
			}
			throw erreur;
		}
	}
};
