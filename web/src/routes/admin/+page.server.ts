import type { ResumeProfil } from '#lib/profil.js';
import { ErreurApi } from '#lib/server/api-resume.js';
import { contexte } from '#lib/server/contexte.js';
import { exigerAdmin } from '#lib/server/garde.js';
import type { PageServerLoad } from './$types';

interface LigneAdmin {
	username: string;
	prenom: string | null;
	emailsProfil: string[];
	modifieLe: string | null;
	emailCompte: string | null;
	admin: boolean;
	inscritLe: string | null;
}

/** Profils de l'API et comptes du site, réunis par username. Les deux listes peuvent
 * différer : un profil créé à la main côté appli n'a pas de compte, un compte dont l'API a
 * perdu le profil n'a plus de profil — l'administrateur doit voir les deux cas. */
export const load: PageServerLoad = async ({ locals, url }) => {
	exigerAdmin(locals.utilisateur, url);
	const ctx = contexte();

	let profils: ResumeProfil[] = [];
	let erreur: string | null = null;
	try {
		profils = await ctx.api.listerProfils();
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		erreur = cause.message;
	}

	const lignes = new Map<string, LigneAdmin>();
	for (const profil of profils) {
		lignes.set(profil.username, {
			username: profil.username,
			prenom: profil.prenom || null,
			emailsProfil: profil.email,
			modifieLe: profil.modifie_le,
			emailCompte: null,
			admin: false,
			inscritLe: null
		});
	}
	for (const compte of ctx.comptes.lister()) {
		const ligne = lignes.get(compte.username) ?? {
			username: compte.username,
			prenom: null,
			emailsProfil: [],
			modifieLe: null,
			emailCompte: null,
			admin: false,
			inscritLe: null
		};
		ligne.emailCompte = compte.email;
		ligne.admin = compte.admin;
		ligne.inscritLe = compte.cree_le;
		lignes.set(compte.username, ligne);
	}

	return {
		lignes: [...lignes.values()].sort((a, b) => a.username.localeCompare(b.username)),
		erreur
	};
};
