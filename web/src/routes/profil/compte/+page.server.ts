import { fail } from '@sveltejs/kit';
import { contexte } from '#lib/server/contexte.js';
import { exigerConnexion } from '#lib/server/garde.js';
import { ErreurIdentifiants, MOT_DE_PASSE_ACTUEL_INCORRECT } from '#lib/server/identifiants.js';
import { COOKIE_SESSION } from '#lib/server/sessions.js';
import { erreurMotDePasse } from '#lib/server/validation.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	const aMotDePasse = contexte().comptes.aUnMotDePasse(utilisateur.id);
	return { email: utilisateur.email, aMotDePasse };
};

/** Le refus d'un formulaire, rangé sous son nom : la page porte deux formulaires et ne
 * doit afficher le message que sous celui qui a été envoyé. */
function refus(
	formulaire: 'motDePasse' | 'adresse',
	erreur: ErreurIdentifiants,
	valeurs: { email?: string } = {},
	statut = erreur.champ === 'motDePasseActuel' ? 403 : erreur.champ === 'general' ? 503 : 422
) {
	return fail(statut, { formulaire, champ: erreur.champ, message: erreur.message, ...valeurs });
}

/** Le mot de passe actuel se devine aussi par ici : les échecs comptent dans la même
 * limite, par adresse du compte, que ceux de la page de connexion. */
function limiteAtteinte(email: string) {
	const ctx = contexte();
	if (ctx.limiteParEmail.autorise(email)) return null;
	const minutes = Math.ceil(ctx.limiteParEmail.attenteSecondes(email) / 60);
	return new ErreurIdentifiants('motDePasseActuel', `Trop de tentatives. Réessayez dans ${minutes} minute(s).`);
}

/** Compte un mauvais mot de passe actuel ; un bon remet le compteur à zéro, comme une
 * connexion réussie — sinon la personne resterait bloquée sur /connexion. `erreur` est nulle
 * quand l'action a réussi, donc que le mot de passe a été vérifié. */
function noterVerification(email: string, erreur: ErreurIdentifiants | null): void {
	const limite = contexte().limiteParEmail;
	if (erreur?.message === MOT_DE_PASSE_ACTUEL_INCORRECT) limite.noter(email);
	else if (erreur?.champ !== 'motDePasseActuel') limite.oublier(email);
}

export const actions: Actions = {
	motDePasse: async ({ locals, request, url, cookies }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const donnees = await request.formData();
		const bloque = limiteAtteinte(utilisateur.email);
		if (bloque) return refus('motDePasse', bloque, {}, 429);
		try {
			await contexte().identifiants.changerMotDePasse(
				utilisateur,
				String(donnees.get('motDePasseActuel') ?? ''),
				String(donnees.get('nouveauMotDePasse') ?? ''),
				cookies.get(COOKIE_SESSION)
			);
		} catch (erreur) {
			if (!(erreur instanceof ErreurIdentifiants)) throw erreur;
			noterVerification(utilisateur.email, erreur);
			return refus('motDePasse', erreur);
		}
		noterVerification(utilisateur.email, null);
		return { formulaire: 'motDePasse', succes: 'Mot de passe changé. Vos autres sessions sont fermées.' };
	},

	adresse: async ({ locals, request, url }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const donnees = await request.formData();
		const email = String(donnees.get('email') ?? '');
		// Le changement d'adresse se prouve par le mot de passe : un compte venu du magic-link
		// doit d'abord en définir un, sinon il buterait sur un refus incompréhensible.
		if (!contexte().comptes.aUnMotDePasse(utilisateur.id)) {
			const sans = new ErreurIdentifiants('general', "Définissez d'abord un mot de passe pour changer d'adresse.");
			return refus('adresse', sans, { email }, 409);
		}
		const bloque = limiteAtteinte(utilisateur.email);
		if (bloque) return refus('adresse', bloque, { email }, 429);
		// Chaque demande écrit à une boîte choisie par l'appelant : plafonnée comme les renvois.
		const ctx = contexte();
		const cle = `adresse:${utilisateur.id}`;
		if (!ctx.limiteRenvoisParEmail.autorise(cle)) {
			const trop = new ErreurIdentifiants('general', 'Trop de demandes. Réessayez dans une heure.');
			return refus('adresse', trop, { email }, 429);
		}
		try {
			const nouvelle = await ctx.identifiants.demanderChangementAdresse(
				utilisateur,
				String(donnees.get('motDePasse') ?? ''),
				email,
				url.origin
			);
			ctx.limiteRenvoisParEmail.noter(cle);
			noterVerification(utilisateur.email, null);
			return {
				formulaire: 'adresse',
				succes: `Un lien vient d'être envoyé à ${nouvelle}. Votre adresse ne changera qu'une fois ce lien ouvert, dans les 24 heures.`
			};
		} catch (erreur) {
			if (!(erreur instanceof ErreurIdentifiants)) throw erreur;
			noterVerification(utilisateur.email, erreur);
			return refus('adresse', erreur, { email });
		}
	},

	definirMotDePasse: async ({ locals, request, url }) => {
		const utilisateur = exigerConnexion(locals.utilisateur, url);
		const donnees = await request.formData();
		const nouveauMotDePasse = String(donnees.get('nouveauMotDePasse') ?? '');

		const erreur = erreurMotDePasse(nouveauMotDePasse);
		if (erreur) {
			return fail(422, { formulaire: 'definirMotDePasse', champ: 'nouveauMotDePasse', message: erreur });
		}

		// Sans mot de passe actuel à vérifier, cette action remplacerait celui d'un compte qui en a
		// un : elle ne vaut que pour le premier.
		if (contexte().comptes.aUnMotDePasse(utilisateur.id)) {
			return fail(409, { formulaire: 'definirMotDePasse', champ: 'general', message: 'Ce compte a déjà un mot de passe.' });
		}

		await contexte().comptes.definirMotDePasse(utilisateur.id, nouveauMotDePasse);
		return {
			formulaire: 'definirMotDePasse',
			succes: 'Mot de passe défini. Vous pouvez maintenant vous connecter avec un mot de passe.'
		};
	}
};
