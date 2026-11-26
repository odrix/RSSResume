/**
 * Le contenu d'une journée tel que l'API le rend, et les deux règles qui le mettent en page.
 *
 * Partagé entre le serveur et la page : le serveur filtre les liens avant de les passer, la
 * page les refiltre avant d'en faire des `href`, la même fonction des deux côtés, pour
 * qu'aucun des deux n'ait à faire confiance à l'autre.
 */

/** Un article cité : « à lire » ou « à surveiller ». */
export interface LienArticle {
	titre: string;
	source: string;
	/** `null` quand l'URL n'est pas http(s) : le titre s'affiche alors sans lien. */
	url: string | null;
}

export interface CategorieJournee {
	categorie: string;
	racontee: boolean;
	resume: string;
	audio: string | null;
	ecoute: string | null;
	articles: LienArticle[];
	a_surveiller: LienArticle[];
}

export interface ContenuJournee {
	date: string;
	audios: { nom: string; taille: number }[];
	ecoute: string | null;
	racontees: number;
	/** L'audio unique de la journée en mode global ; `null` en mode par catégorie. */
	montage: { audio: string | null; ecoute: string | null } | null;
	/** La phrase d'une journée sans article ; `null` sinon. */
	raison: string | null;
	/** Vrai tant que la tournée écrit la journée : ni contenu ni raison, pas encore. */
	en_cours: boolean;
	categories: CategorieJournee[];
}

/** L'heure du passage quotidien, et le prochain, en ISO 8601 avec fuseau. */
export interface Passage {
	heure: string;
	fuseau: string;
	prochain: string;
}

const FORMAT_DATE = new Intl.DateTimeFormat('fr-FR', {
	weekday: 'long',
	day: 'numeric',
	month: 'long',
	year: 'numeric',
	timeZone: 'UTC'
});

/** « Vendredi 21 novembre 2026 ». En UTC : la date ISO est un jour, pas un instant, et le
 * fuseau du serveur ne doit pas la faire glisser à la veille. Partagée par la liste des
 * résumés et le titre des pistes du lecteur. */
export function dateLisible(iso: string): string {
	const texte = FORMAT_DATE.format(new Date(`${iso}T00:00:00Z`));
	return texte.charAt(0).toUpperCase() + texte.slice(1);
}

/** L'URL si elle mène à une page web, `null` sinon.
 *
 * Svelte échappe le texte d'un attribut, pas son sens : un `href="javascript:…"` reste
 * exécutable au clic. Les URL viennent des flux, que n'importe qui écrit ; seul http(s)
 * passe, avec un hôte, la même règle que `lien_sur` côté API. */
export function urlSure(url: string | null | undefined): string | null {
	if (typeof url !== 'string') return null;
	const texte = url.trim();
	let analysee: URL;
	try {
		analysee = new URL(texte);
	} catch {
		return null;
	}
	if (analysee.protocol !== 'http:' && analysee.protocol !== 'https:') return null;
	// `new URL` répare `http:hote` ou `https:///hote` en leur trouvant un hôte ; l'API, elle,
	// les refuse faute de netloc. Le site s'en tient à la forme écrite, pour refuser pareil.
	if (!analysee.host || !/^https?:\/\/[^/\\]/i.test(texte)) return null;
	return texte;
}

/** Les paragraphes d'un résumé, coupés sur les lignes vides comme dans l'email.
 *
 * Le résumé est écrit pour la voix, sans balisage : sa seule structure est le passage à la
 * ligne. Le découper ici permet de rendre chaque paragraphe en texte, sans `{@html}`. */
export function paragraphes(texte: string): string[] {
	return (texte ?? '')
		.split(/\n[ \t]*\n/)
		.map((morceau) => morceau.trim())
		.filter(Boolean);
}

/** Un préfixe numérique en tête de libellé : « 11 - … » commence par 11. */
const PREFIXE_NUMERIQUE = /^\s*(\d+)/;

/** Le texte replié pour comparaison, comme `casefold_ascii` côté API : casse repliée,
 * accents retirés, pour que la comparaison ne dépende ni de la casse ni des accents. */
function casefoldAscii(texte: string): string {
	return (texte ?? '')
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase();
}

/** La clé de tri naturel d'un libellé : `[0, numéro, reste]` s'il commence par un nombre,
 * `[1, 0, libellé replié]` sinon. Même règle que `cle_tri_naturel` côté API, pour que le
 * site et l'email classent les catégories dans le même ordre. */
function cleTriNaturel(libelle: string): [number, number, string] {
	const prefixe = PREFIXE_NUMERIQUE.exec(libelle ?? '');
	if (prefixe) {
		return [0, Number(prefixe[1]), casefoldAscii(libelle.slice(prefixe[0].length))];
	}
	return [1, 0, casefoldAscii(libelle)];
}

/** Comparateur de tri naturel : « 2 … » avant « 11 … », les libellés sans préfixe
 * numérique après, par ordre alphabétique, et à numéro égal le texte départage.
 *
 * Un tri de chaînes plain classerait « 11 » avant « 2 », ce qui contredit la numérotation
 * choisie pour les catégories. */
export function triNaturel(a: string, b: string): number {
	const [ga, na, ra] = cleTriNaturel(a);
	const [gb, nb, rb] = cleTriNaturel(b);
	if (ga !== gb) return ga - gb;
	if (na !== nb) return na - nb;
	return ra < rb ? -1 : ra > rb ? 1 : 0;
}

/** Les catégories d'une journée dans l'ordre d'affichage : le tri naturel de leur
 * libellé, le même que celui des sections de l'email. */
export function categoriesTriees(contenu: ContenuJournee): CategorieJournee[] {
	return [...contenu.categories].sort((a, b) => triNaturel(a.categorie, b.categorie));
}
