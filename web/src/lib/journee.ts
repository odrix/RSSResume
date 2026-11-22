/**
 * Le contenu d'une journée tel que l'API le rend, et les deux règles qui le mettent en page.
 *
 * Partagé entre le serveur et la page : le serveur filtre les liens avant de les passer, la
 * page les refiltre avant d'en faire des `href` — la même fonction des deux côtés, pour
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

/** L'URL si elle mène à une page web, `null` sinon.
 *
 * Svelte échappe le texte d'un attribut, pas son sens : un `href="javascript:…"` reste
 * exécutable au clic. Les URL viennent des flux, que n'importe qui écrit ; seul http(s)
 * passe, avec un hôte — la même règle que `lien_sur` côté API. */
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
