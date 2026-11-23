import type { ResumeProfil } from '#lib/profil.js';
import type { CoutsProfil } from '#lib/server/api-resume.js';
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
	derniereConnexionLe: string | null;
	consultations7j: number;
	desabonne: boolean;
	couts7j: CoutsProfil['couts_7j'] | null;
	couts30j: CoutsProfil['couts_30j'] | null;
	/** Faux pour un compte dont l'adresse attend sa confirmation (purgé après sept jours). */
	confirme: boolean;
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
			inscritLe: null,
			derniereConnexionLe: null,
			consultations7j: 0,
			desabonne: false,
			couts7j: null,
			couts30j: null,
			confirme: true
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
			inscritLe: null,
			derniereConnexionLe: null,
			consultations7j: 0,
			desabonne: false,
			couts7j: null,
			couts30j: null,
			confirme: true
		};
		ligne.emailCompte = compte.email;
		ligne.admin = compte.admin;
		ligne.inscritLe = compte.creeLe;
		ligne.derniereConnexionLe = compte.derniereConnexionLe;
		ligne.consultations7j = ctx.comptes.consultationsSeptJours(compte.id);
		ligne.confirme = compte.confirme;
		ligne.desabonne = ligne.modifieLe !== null && ligne.emailsProfil.length === 0;
		lignes.set(compte.username, ligne);
	}

	for (const ligne of lignes.values()) {
		ligne.desabonne = ligne.modifieLe !== null && ligne.emailsProfil.length === 0;
		if (ligne.modifieLe !== null) {
			try {
				const couts = await ctx.api.lireCouts(ligne.username);
				ligne.couts7j = couts.couts_7j;
				ligne.couts30j = couts.couts_30j;
			} catch (cause) {
				if (!(cause instanceof ErreurApi)) throw cause;
			}
		}
	}

	const maintenant = Date.now();
	const limite7 = new Date(maintenant - 6 * 24 * 60 * 60 * 1000).toISOString();
	const limite30 = new Date(maintenant - 29 * 24 * 60 * 60 * 1000).toISOString();
	const comptesConfirmes = ctx.comptes.lister().filter((compte) => compte.confirme);

	const coutsComplets = [...lignes.values()].map((ligne) => ligne.couts7j).filter(
		(couts): couts is CoutsProfil['couts_7j'] => couts !== null
	);
	const coutTotalSemaine = coutsComplets.every((couts) => couts.tarification_complete)
		? coutsComplets.reduce((total, couts) => total + (couts.total ?? 0), 0)
		: null;
	const deviseSemaine = coutsComplets.find((couts) => couts.devise)?.devise ?? null;
	const modelesSansTarifSemaine = [...new Set(coutsComplets.flatMap((couts) => couts.modeles_sans_tarif))];

	return {
		lignes: [...lignes.values()].sort((a, b) => a.username.localeCompare(b.username)),
		erreur,
		inscriptions7j: comptesConfirmes.filter((compte) => compte.creeLe >= limite7).length,
		inscriptions30j: comptesConfirmes.filter((compte) => compte.creeLe >= limite30).length,
		coutTotalSemaine,
		deviseSemaine,
		modelesSansTarifSemaine
	};
};
