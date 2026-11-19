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

/** Ce que l'API rend d'un profil, intégralement. */
export interface Profil {
	username: string;
	profil: string;
	stack: ComposantStack[];
	email: string[];
	prenom: string;
	modifie_le: string;
}

/** Une ligne de la liste des profils : le texte et la stack n'y sont pas. */
export interface ResumeProfil {
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
}

/** Une ligne de l'éditeur de stack : deux champs texte, quel que soit le composant. */
export interface LigneStack {
	nom: string;
	alias: string;
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

/** Relit le formulaire « Mon profil ». La validation de fond reste celle de l'API : elle
 * seule sait ce que l'appli de résumé accepte, et ses 422 sont affichées telles quelles. */
export function lireFormulaireProfil(donnees: FormData): ProfilSaisi {
	const noms = donnees.getAll('stack_nom').map(String);
	const alias = donnees.getAll('stack_alias').map(String);
	return {
		profil: String(donnees.get('profil') ?? '').trim(),
		prenom: String(donnees.get('prenom') ?? '').trim(),
		email: decouper(String(donnees.get('email') ?? ''), /[\s,;]+/),
		stack: depuisLignes(noms.map((nom, i) => ({ nom, alias: alias[i] ?? '' })))
	};
}

function decouper(texte: string, separateur: RegExp): string[] {
	return texte
		.split(separateur)
		.map((morceau) => morceau.trim())
		.filter(Boolean);
}
