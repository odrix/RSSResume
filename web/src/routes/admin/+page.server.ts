import { REGIMES, type ResumeProfil, type Securite } from '#lib/profil.js';

import { ErreurApi, type CoutsProfil, type Retour } from '#lib/server/api-resume.js';

import { contexte } from '#lib/server/contexte.js';

import { exigerAdmin } from '#lib/server/garde.js';

import type { PageServerLoad } from './$types';

type Onglet = 'profils' | 'stats' | 'retours';

const ONGLETS: Onglet[] = ['profils', 'stats', 'retours'];

const LIBELLE_PERSONNALISE = 'Personnalisé';
const LIBELLE_TOUTES_CATEGORIES = 'Toutes les catégories';

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
	/** Régime de sécurité du profil ; `null` sans profil. */
	securite: Securite | null;
	/** Libellés des catégories cochées ; `null` quand le profil suit tout le catalogue. */
	categoriesLibelles: string[] | null;
	/** Libellé du gabarit dont le texte du profil est repris, « Personnalisé » sinon. */
	profilChoisi: string | null;
	journees7j: number;
	journees30j: number;
	couts7j: CoutsProfil['couts_7j'] | null;
	couts30j: CoutsProfil['couts_30j'] | null;
	/** Faux pour un compte dont l'adresse attend sa confirmation (purgé après sept jours). */
	confirme: boolean;
}

/** Une part d'un camembert ou d'une barre : un libellé et le nombre de personnes. */
export interface Tranche {
	libelle: string;
	nombre: number;
}

/** Profils de l'API et comptes du site, réunis par username. Les deux listes peuvent
 * différer : un profil créé à la main côté appli n'a pas de compte, un compte dont l'API a
 * perdu le profil n'a plus de profil, l'administrateur doit voir les deux cas. */

export const load: PageServerLoad = async ({ locals, url }) => {

	exigerAdmin(locals.utilisateur, url);
	const ctx = contexte();

	const ongletBrut = url.searchParams.get('onglet');
	const onglet: Onglet = (ONGLETS as string[]).includes(ongletBrut ?? '') ? (ongletBrut as Onglet) : 'profils';

	let profils: ResumeProfil[] = [];
	let erreur: string | null = null;
	try {
		profils = await ctx.api.listerProfils();
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		erreur = cause.message;
	}

	// Les gabarits servent à nommer le profil choisi d'après le texte du profil : un texte
	// repris tel quel d'un gabarit porte le libellé de ce gabarit, les autres sont « Personnalisé ».
	let gabarits: { libelle: string; profil: string }[] = [];
	try {
		gabarits = (await ctx.api.listerGabarits()).map(({ libelle, profil }) => ({ libelle, profil }));
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		// Sans gabarits, tout profil est « Personnalisé » : la page marche quand même.
	}

	const lignes = new Map<string, LigneAdmin>();

	const ligneVide = (username: string): LigneAdmin => ({
		username,
		prenom: null,
		emailsProfil: [],
		modifieLe: null,
		emailCompte: null,
		admin: false,
		inscritLe: null,
		derniereConnexionLe: null,
		consultations7j: 0,
		desabonne: false,
		securite: null,
		categoriesLibelles: null,
		profilChoisi: null,
		journees7j: 0,
		journees30j: 0,
		couts7j: null,
		couts30j: null,
		confirme: true
	});

	for (const profil of profils) {
		lignes.set(profil.username, { ...ligneVide(profil.username), prenom: profil.prenom || null, emailsProfil: profil.email, modifieLe: profil.modifie_le });
	}
	for (const compte of ctx.comptes.lister()) {
		const ligne = lignes.get(compte.username) ?? ligneVide(compte.username);
		ligne.emailCompte = compte.email;
		ligne.admin = compte.admin;
		ligne.inscritLe = compte.creeLe;
		ligne.derniereConnexionLe = compte.derniereConnexionLe;
		ligne.consultations7j = ctx.comptes.consultationsSeptJours(compte.id);
		ligne.confirme = compte.confirme;
		lignes.set(compte.username, ligne);
	}

	// Après `exigerAdmin`, et jamais avant : la liste ne part de l'API que pour qui a le droit
	// de la voir. Une erreur à part de celle des profils : l'une n'empêche pas l'autre.
	let retours: Retour[] = [];
	let erreurRetours: string | null = null;
	try {
		retours = await ctx.retours.lister();
	} catch (cause) {
		if (!(cause instanceof ErreurApi)) throw cause;
		erreurRetours = cause.message;
	}

	const maintenant = Date.now();
	const limite7 = new Date(maintenant - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
	const limite30 = new Date(maintenant - 29 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

	for (const ligne of lignes.values()) {
		ligne.desabonne = ligne.modifieLe !== null && ligne.emailsProfil.length === 0;
		if (ligne.modifieLe === null) continue;
		// Trois lectures par profil, en parallèle : le détail du profil (sécurité, catégories),
		// ses journées produites, et leurs coûts. Chacune peut échouer seule sans perdre les autres.
		const [detail, journees, couts] = await Promise.all([
			ctx.api.lireProfil(ligne.username).catch((cause: unknown) => {
				if (!(cause instanceof ErreurApi)) throw cause;
				return null;
			}),
			ctx.api.listerJournees(ligne.username).catch((cause: unknown) => {
				if (!(cause instanceof ErreurApi)) throw cause;
				return null;
			}),
			ctx.api.lireCouts(ligne.username).catch((cause: unknown) => {
				if (!(cause instanceof ErreurApi)) throw cause;
				return null;
			})
		]);
		if (detail) {
			ligne.securite = detail.securite;
			ligne.categoriesLibelles = detail.categories ?? null;
			const gabarit = gabarits.find((g) => g.profil === detail.profil);
			ligne.profilChoisi = gabarit ? gabarit.libelle : LIBELLE_PERSONNALISE;
		}
		if (journees) {
			ligne.journees7j = journees.filter((journee) => journee.date >= limite7).length;
			ligne.journees30j = journees.filter((journee) => journee.date >= limite30).length;
		}
		if (couts) {
			ligne.couts7j = couts.couts_7j;
			ligne.couts30j = couts.couts_30j;
		}
	}

	const comptesConfirmes = ctx.comptes.lister().filter((compte) => compte.confirme);

	// Un coût inconnu vaut 0 plutôt qu'un « ? » : mieux que rien, et les quantités ne le comptent pas.
	const coutsComplets = [...lignes.values()].map((ligne) => ligne.couts7j).filter(
		(couts): couts is CoutsProfil['couts_7j'] => couts !== null
	);
	const coutTotalSemaine = coutsComplets.reduce((total, couts) => total + (couts.total ?? 0), 0);
	const deviseSemaine = coutsComplets.find((couts) => couts.devise)?.devise ?? null;
	const modelesSansTarifSemaine = [...new Set(coutsComplets.flatMap((couts) => couts.modeles_sans_tarif))];

	const avecProfil = [...lignes.values()].filter((ligne) => ligne.modifieLe !== null);

	const compter = (libelles: (string | null)[]): Tranche[] => {
		const comptes = new Map<string, number>();
		for (const libelle of libelles) {
			const cle = libelle ?? LIBELLE_PERSONNALISE;
			comptes.set(cle, (comptes.get(cle) ?? 0) + 1);
		}
		return [...comptes.entries()]
			.map(([libelle, nombre]) => ({ libelle, nombre }))
			.sort((a, b) => b.nombre - a.nombre || a.libelle.localeCompare(b.libelle));
	};

	const repartitionProfils = compter(avecProfil.map((ligne) => ligne.profilChoisi));
	const repartitionSecurite = compter(avecProfil.map((ligne) => ligne.securite));
	const parCategorie = compter(
		avecProfil.flatMap((ligne) => (ligne.categoriesLibelles === null ? [LIBELLE_TOUTES_CATEGORIES] : ligne.categoriesLibelles))
	);

	return {
		onglet,
		lignes: [...lignes.values()].sort((a, b) => a.username.localeCompare(b.username)),
		erreur,
		inscriptions7j: comptesConfirmes.filter((compte) => compte.creeLe >= limite7).length,
		inscriptions30j: comptesConfirmes.filter((compte) => compte.creeLe >= limite30).length,
		coutTotalSemaine,
		deviseSemaine,
		modelesSansTarifSemaine,
		repartitionProfils,
		repartitionSecurite,
		parCategorie,
		retours,
		erreurRetours
	};
};
