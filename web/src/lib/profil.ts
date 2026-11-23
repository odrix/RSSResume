/**
 * Le document d'une personne tel que l'API de résumé le porte, et sa saisie au formulaire.
 *
 * Partagé entre le serveur et la page : la page affiche la stack que le serveur a lue, le
 * serveur relit ce que la page a envoyé, et les deux doivent s'entendre sur ce qu'est un
 * composant. Le format est celui de `rssresume/profil.py` — un composant est un nom seul,
 * ou un nom suivi de ses alias.
 */

/** Un composant surveillé : `"Traefik"` ou `{"nom": "Keycloak", "alias": ["RH-SSO"]}`. */
export type ComposantStack = string | { nom: string; alias?: string[] };

/** Les trois degrés de détail dus aux vulnérabilités. */
export type Securite = 'exploitant' | 'decideur' | 'curieux';

/** Un régime de sécurité tel que la page le présente. */
export interface Regime {
	valeur: Securite;
	libelle: string;
	/** Une ligne, dite en termes de métier : la valeur seule ne dit rien à qui ne connaît pas
	 * la consigne qu'elle choisit côté appli. */
	explication: string;
}

/** Les régimes, dans l'ordre de `Securite` (`rssresume/profil.py`), du plus détaillé au plus bref. */
export const REGIMES: Regime[] = [
	{
		valeur: 'exploitant',
		libelle: 'Exploitant',
		explication:
			'vous administrez des serveurs ou des logiciels : tout le détail des failles, versions comprises, gradué selon votre stack.'
	},
	{
		valeur: 'decideur',
		libelle: 'Décideur',
		explication:
			'vous décidez sans appliquer les correctifs : une phrase par faille, sans versions, sauf sur un composant de votre stack.'
	},
	{
		valeur: 'curieux',
		libelle: 'Curieux',
		explication: "vous suivez la sécurité de loin : seulement les failles exploitées ou qui font l'actualité, en une phrase."
	}
];

/** Une rubrique du scoring, propre à un métier : ce que l'appli range sous `axes`. */
export interface Axe {
	slug: string;
	libelle: string;
	description: string;
}

/** Les bornes de `rssresume/axes.py` : en dessous il n'y a rien à regrouper, au-delà le
 * modèle range au hasard entre des rubriques voisines. */
export const NOMBRE_MIN_AXES = 3;
export const NOMBRE_MAX_AXES = 6;
/** Les rubriques d'un profil qui n'en déclare pas : la page les nomme pour que « laisser
 * vide » veuille dire quelque chose. */
export const AXES_PAR_DEFAUT = ['reglementaire', 'cyber', 'marche', 'stack', 'autre'];
/** Le motif d'un slug dans `rssresume/axes.py` : il devient le tag FreshRSS `theme-<slug>`. */
const MOTIF_SLUG = /^[a-z][a-z0-9-]{1,23}$/;
const LONGUEUR_MAX_SLUG = 24;

/** Une catégorie que la personne peut suivre, telle que `GET …/profils/{u}/categories` la rend. */
export interface CategorieProposee {
	libelle: string;
	description: string;
	/** Privée : montrée à ses seuls propriétaires, que l'API ne nomme pas. */
	privee: boolean;
}

/** Les catégories à cocher. `ouvert` : aucun catalogue n'est déclaré, tout est suivi et il
 * n'y a rien à proposer. */
export interface CategoriesProposees {
	ouvert: boolean;
	categories: CategorieProposee[];
}

/** Un profil de départ proposé à l'inscription, tel que `GET /api/v1/gabarits` le rend.
 * `metier` n'identifie que le gabarit : il n'est jamais envoyé avec un profil. */
export interface Gabarit {
	metier: string;
	libelle: string;
	profil: string;
	stack: ComposantStack[];
	securite: Securite;
	axes: Axe[];
	categories: string[];
}

/** Ce que l'API rend d'un profil, intégralement. */
export interface Profil {
	/** UUID attribué par l'API à la création, immuable. Le site adresse pourtant les
	 * profils par username : c'est lui qui relie un profil à un compte. */
	id: string;
	username: string;
	profil: string;
	stack: ComposantStack[];
	email: string[];
	prenom: string;
	securite: Securite;
	/** Absents quand le profil n'en déclare pas : l'appli prend alors ses axes par défaut
	 * et tout le catalogue des catégories. */
	axes?: Axe[];
	categories?: string[];
	modifie_le: string;
}

/** Une ligne de la liste des profils : le texte et la stack n'y sont pas. */
export interface ResumeProfil {
	id: string;
	username: string;
	prenom: string;
	email: string[];
	modifie_le: string;
}

/** Ce que la personne écrit, c'est-à-dire tout sauf l'identité et l'horodatage. */
export interface ProfilSaisi {
	profil: string;
	stack: ComposantStack[];
	email: string[];
	prenom: string;
	securite: Securite;
	/** `undefined` : la page ne les a pas montrés, l'enregistrement garde ceux du profil.
	 * Liste vide : retour aux rubriques par défaut. */
	axes?: Axe[];
	/** `undefined` : la section n'a pas été montrée, l'enregistrement garde la valeur
	 * actuelle. `null` : tout est coché, la clé est retirée — le profil suit alors tout le
	 * catalogue, y compris les catégories ajoutées plus tard. Une liste : celles cochées. */
	categories?: string[] | null;
}

/** Une ligne de l'éditeur de stack : deux champs texte, quel que soit le composant. */
export interface LigneStack {
	nom: string;
	alias: string;
}

/** Une ligne de l'éditeur d'axes. `slug` est vide pour un axe nouveau : il est fabriqué à
 * l'enregistrement, la personne n'a pas à connaître les tags. */
export interface LigneAxe {
	slug: string;
	libelle: string;
	description: string;
}

/** Une saisie refusée par le site avant d'atteindre l'API : le champ, et le message. */
export interface RefusSaisie {
	champ: string;
	message: string;
}

/** Le texte proposé à qui s'inscrit sans en écrire un.
 *
 * Volontairement court et lisible plutôt que le profil par défaut de l'appli : la
 * personne le relira dans « Mon profil », et c'est un point de départ à réécrire, pas
 * un réglage qu'on oublie. */
export const PROFIL_PAR_DEFAUT = `Professionnel de la tech. Veille quotidienne sur ce qui change la façon de concevoir, de livrer et d'exploiter un logiciel.

Axes de veille pertinents :
- cyber : failles exploitables sur des composants répandus, incidents majeurs.
- stack : versions majeures, fins de support, ruptures de compatibilité.
- reglementaire : ce que la loi impose au logiciel et aux données.

Ne sont PAS pertinents : le hardware grand public, les levées de fonds sans conséquence technique.`;

export function versLignes(stack: ComposantStack[]): LigneStack[] {
	return stack.map((composant) =>
		typeof composant === 'string'
			? { nom: composant, alias: '' }
			: { nom: composant.nom, alias: (composant.alias ?? []).join(', ') }
	);
}

/** Les lignes vides sont ignorées : l'éditeur en laisse une libre pour la saisie suivante. */
export function depuisLignes(lignes: LigneStack[]): ComposantStack[] {
	const stack: ComposantStack[] = [];
	for (const ligne of lignes) {
		const nom = ligne.nom.trim();
		if (!nom) continue;
		const alias = decouper(ligne.alias, /,/);
		stack.push(alias.length ? { nom, alias } : nom);
	}
	return stack;
}

/** Les lignes de l'éditeur d'axes : celles du profil, puis des lignes libres jusqu'à
 * `nombre`. Des champs toujours présents plutôt qu'un bouton « ajouter » : la page marche
 * sans JavaScript, et six lignes suffisent au plus grand nombre d'axes accepté. */
export function versLignesAxes(axes: Axe[] | undefined, nombre = NOMBRE_MAX_AXES): LigneAxe[] {
	const lignes: LigneAxe[] = (axes ?? []).map(({ slug, libelle, description }) => ({ slug, libelle, description }));
	while (lignes.length < nombre) lignes.push({ slug: '', libelle: '', description: '' });
	return lignes;
}

/** Les axes saisis. Une ligne sans libellé ni description est ignorée ; un axe existant
 * garde son slug même renommé — le changer séparerait l'axe des articles déjà tagués —,
 * un nouveau en reçoit un tiré de son libellé, distinct des autres. */
export function depuisLignesAxes(lignes: LigneAxe[]): Axe[] {
	const remplies = lignes
		.map((ligne) => ({
			slug: ligne.slug.trim(),
			libelle: ligne.libelle.trim(),
			description: ligne.description.trim()
		}))
		.filter((ligne) => ligne.libelle || ligne.description);
	const pris = new Set(remplies.map((ligne) => ligne.slug).filter(Boolean));
	return remplies.map((ligne) => {
		if (ligne.slug) return ligne;
		const slug = slugAxe(ligne.libelle, pris);
		pris.add(slug);
		return { ...ligne, slug };
	});
}

/** Un slug valide pour `rssresume/axes.py` (`[a-z][a-z0-9-]{1,23}`), tiré du libellé :
 * accents retirés, tout le reste en tirets. Déjà pris, il reçoit un suffixe `-2`, `-3`… :
 * deux axes au même slug porteraient le même tag, et l'API les refuserait. */
export function slugAxe(libelle: string, pris: Iterable<string> = []): string {
	const occupes = new Set(pris);
	let base = libelle
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '');
	// Un slug commence par une lettre et fait deux caractères au moins : « 5G » ou « Q »
	// deviennent axe-5g, axe-q ; un libellé vide, axe.
	if (!MOTIF_SLUG.test(couperSlug(base, LONGUEUR_MAX_SLUG))) {
		base = base ? `axe-${base}` : 'axe';
	}
	base = couperSlug(base, LONGUEUR_MAX_SLUG);
	let slug = base;
	for (let rang = 2; occupes.has(slug); rang++) {
		const suffixe = `-${rang}`;
		slug = couperSlug(base, LONGUEUR_MAX_SLUG - suffixe.length) + suffixe;
	}
	return slug;
}

function couperSlug(slug: string, longueur: number): string {
	return slug.slice(0, longueur).replace(/-+$/, '');
}

/** Les catégories que la page peut faire cocher : aucune quand le catalogue est ouvert ou
 * que la liste n'a pas pu être lue — la section est alors masquée. */
export function categoriesACocher(proposees: CategoriesProposees | null): CategorieProposee[] {
	return proposees && !proposees.ouvert ? proposees.categories : [];
}

/** Le profil pré-rempli d'un gabarit : son texte, son régime et ses axes remplacent les
 * siens. La stack, les adresses et le prénom restent : un gabarit ne sait rien de ce que la
 * personne exploite, ni de qui elle est.
 *
 * Ses catégories ne sont reprises que parmi celles proposées à la personne, sous leur
 * libellé proposé : un gabarit est écrit pour tout le monde, et une catégorie qu'elle ne
 * peut pas suivre ne doit ni apparaître cochée ni partir à l'API. Si aucune ne reste, tout
 * est coché plutôt que rien — rien serait refusé à l'enregistrement. Sans catégories à
 * cocher, la page ne les montre pas : celles du profil sont gardées telles quelles. */
export function depuisGabarit(
	profil: ProfilSaisi | null,
	gabarit: Gabarit,
	proposees: CategoriesProposees | null
): ProfilSaisi {
	const aCocher = categoriesACocher(proposees);
	let categories = profil?.categories;
	if (aCocher.length) {
		const duGabarit = new Set(gabarit.categories.map(cleCategorie));
		const retenues = aCocher
			.map((categorie) => categorie.libelle)
			.filter((libelle) => duGabarit.has(cleCategorie(libelle)));
		categories = retenues.length ? retenues : null;
	}
	return {
		profil: gabarit.profil,
		stack: profil?.stack ?? [],
		email: profil?.email ?? [],
		prenom: profil?.prenom ?? '',
		securite: gabarit.securite,
		axes: gabarit.axes,
		categories
	};
}

/** La forme sous laquelle deux libellés se comparent, comme `cle_categorie` côté appli :
 * rognée, sans casse ni accents. */
function cleCategorie(libelle: string): string {
	return libelle
		.trim()
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase();
}

/** Ce que le site refuse avant l'API. Aucune catégorie cochée : l'API lirait la liste vide
 * comme une clé absente, c'est-à-dire « tout » — l'exact contraire de ce qui a été coché. */
export function erreurSaisieProfil(saisie: ProfilSaisi): RefusSaisie | null {
	if (saisie.categories && !saisie.categories.length) {
		return {
			champ: 'categories',
			message: 'Cochez au moins une catégorie : un résumé qui ne suit rien serait toujours vide.'
		};
	}
	return null;
}

/** Relit le formulaire « Mon profil ». La validation de fond reste celle de l'API : elle
 * seule sait ce que l'appli de résumé accepte, et ses 422 sont affichées sous leur champ.
 *
 * Axes et catégories ne sont relus que si la page les a montrés (marqueurs cachés
 * `axes_edites`, `categories_editees`) : sinon ils restent `undefined`, et l'enregistrement
 * garde ceux du profil au lieu de les effacer. Toutes les catégories proposées cochées
 * donnent `null` : la clé sera retirée, pour que le profil suive aussi les futures. */
export function lireFormulaireProfil(donnees: FormData): ProfilSaisi {
	const noms = donnees.getAll('stack_nom').map(String);
	const alias = donnees.getAll('stack_alias').map(String);
	const saisie: ProfilSaisi = {
		profil: String(donnees.get('profil') ?? '').trim(),
		prenom: String(donnees.get('prenom') ?? '').trim(),
		email: decouper(String(donnees.get('email') ?? ''), /[\s,;]+/),
		stack: depuisLignes(noms.map((nom, i) => ({ nom, alias: alias[i] ?? '' }))),
		securite: String(donnees.get('securite') ?? 'exploitant') as Securite
	};
	if (donnees.has('axes_edites')) {
		const slugs = donnees.getAll('axe_slug').map(String);
		const descriptions = donnees.getAll('axe_description').map(String);
		saisie.axes = depuisLignesAxes(
			donnees
				.getAll('axe_libelle')
				.map(String)
				.map((libelle, i) => ({ slug: slugs[i] ?? '', libelle, description: descriptions[i] ?? '' }))
		);
	}
	if (donnees.has('categories_editees')) {
		const cochees = donnees.getAll('categories').map(String);
		const proposees = donnees.getAll('categories_proposees').map(String);
		const toutes = proposees.length > 0 && proposees.every((libelle) => cochees.includes(libelle));
		saisie.categories = toutes ? null : cochees;
	}
	return saisie;
}

/** La saisie telle que la page la réaffiche après un refus : les slugs fabriqués pour les
 * axes nouveaux en sont retirés. Réécrits dans le champ caché, ils passeraient au prochain
 * envoi pour ceux d'axes existants, et resteraient figés même le libellé corrigé
 * (« Qualté » donnerait `qualte` pour toujours). Seuls restent les slugs envoyés par la
 * page, qui viennent du profil enregistré. */
export function saisieAReafficher(saisie: ProfilSaisi, donnees: FormData): ProfilSaisi {
	if (!saisie.axes) return saisie;
	const existants = new Set(
		donnees
			.getAll('axe_slug')
			.map((slug) => String(slug).trim())
			.filter(Boolean)
	);
	return {
		...saisie,
		axes: saisie.axes.map((axe) => (existants.has(axe.slug) ? axe : { ...axe, slug: '' }))
	};
}

function decouper(texte: string, separateur: RegExp): string[] {
	return texte
		.split(separateur)
		.map((morceau) => morceau.trim())
		.filter(Boolean);
}
