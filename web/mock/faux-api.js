/**
 * Une fausse API de résumé, en mémoire, qui tient le contrat de `API.md`.
 *
 * Un seul gestionnaire `Request → Response` pour deux usages : les tests le passent au
 * client à la place de `fetch`, et `api-resume.mjs` le sert en HTTP pour le développement.
 * Écrit en JavaScript (typé par JSDoc) pour que Node le lance sans compilation.
 */

const MOTIF_USERNAME = /^[a-z0-9][a-z0-9_-]{1,31}$/;

/**
 * @typedef {string | { nom: string, alias?: string[] }} ComposantStack
 * @typedef {{ slug: string, libelle: string, description: string }} AxeStocke
 * @typedef {{ id: string, username: string, profil: string, stack: ComposantStack[], email: string[], prenom: string, securite: 'exploitant' | 'decideur' | 'curieux', axes?: AxeStocke[], categories?: string[], modifie_le: string }} ProfilStocke
 * @typedef {{ metier: string, libelle: string, profil: string, stack: ComposantStack[], securite: 'exploitant' | 'decideur' | 'curieux', axes: AxeStocke[], categories: string[] }} GabaritStocke
 * @typedef {{ titre: string, source: string, url: string | null }} LienStocke
 * @typedef {{ categorie: string, racontee: boolean, resume: string, audio: string | null, ecoute: string | null, articles: LienStocke[], a_surveiller: LienStocke[] }} CategorieStockee
 * @typedef {{ ecoute?: string | null, racontees?: number, montage?: { audio: string | null, ecoute: string | null } | null, raison?: string | null, en_cours?: boolean, categories?: CategorieStockee[] }} ContenuStocke
 * @typedef {{ date: string, audios: { nom: string, octets: Uint8Array }[], contenu?: ContenuStocke }} JourneeStockee
 */

/**
 * Le catalogue des catégories : toutes celles des gabarits ci-dessous, publiques, plus une
 * privée de `moi` et une privée de `bea`, de quoi voir la règle de visibilité. Vide de
 * propriétaires, une catégorie est publique, comme dans `rssresume/categories.py`.
 * @typedef {{ libelle: string, description: string, proprietaires: string[] }} CategorieStockeeCatalogue
 * @type {CategorieStockeeCatalogue[]}
 */
export const CATALOGUE_DEMO = [
	{ libelle: '1 - Alertes et avis CERT-FR ANSSI', description: "Les avis de sécurité de l'ANSSI.", proprietaires: [] },
	{ libelle: '11 - Qualite logicielle et tests', description: 'Tests, revue de code, outillage.', proprietaires: [] },
	{ libelle: 'Cybersécurité', description: 'Menaces, failles et incidents.', proprietaires: [] },
	{ libelle: 'Réglementaire', description: 'Ce que la loi impose au logiciel et aux données.', proprietaires: [] },
	{ libelle: 'Tech generaliste', description: "L'actualité technique au sens large.", proprietaires: [] },
	{ libelle: 'Veille concurrentielle', description: 'Les mouvements des concurrents.', proprietaires: ['moi'] },
	{ libelle: 'Veille interne', description: "La veille d'une autre équipe.", proprietaires: ['bea'] }
];

/** Le passage annoncé par la fausse API : celui du déploiement par défaut. */
const HEURE_PASSAGE = '04:00';
const FUSEAU_PASSAGE = 'Europe/Paris';

/**
 * Quelques gabarits, plus courts que ceux de `rssresume/gabarits.json` mais de même forme :
 * de quoi essayer le choix du métier, et un `decideur` pour voir le régime suivre.
 * @type {GabaritStocke[]}
 */
export const GABARITS_DEMO = [
	{
		metier: 'cto',
		libelle: 'CTO, direction technique',
		profil:
			"CTO d'un éditeur de logiciel. Veille sur ce qui engage l'architecture, la sécurité et l'équipe.\n\nAxes de veille pertinents :\n- architecture : plates-formes, cloud, décisions structurantes.\n- cyber : failles majeures et incidents qui touchent un éditeur.",
		stack: [],
		securite: 'decideur',
		axes: [
			{ slug: 'architecture', libelle: 'Architecture', description: 'plates-formes, cloud et décisions structurantes' },
			{ slug: 'cyber', libelle: 'Cybersécurité', description: 'failles majeures et incidents' }
		],
		categories: ['Tech generaliste', 'Cybersécurité']
	},
	{
		metier: 'developpeur',
		libelle: 'Développeur',
		profil:
			"Développeur. Veille sur les langages, les outils et les pratiques du quotidien.\n\nAxes de veille pertinents :\n- langages : versions, nouveautés, fins de support.\n- qualite : tests, revue, outillage.",
		stack: [],
		securite: 'exploitant',
		axes: [
			{ slug: 'langages', libelle: 'Langages', description: 'versions, nouveautés et fins de support' },
			{ slug: 'qualite', libelle: 'Qualité', description: 'tests, revue et outillage' }
		],
		categories: ['Tech generaliste', '11 - Qualite logicielle et tests']
	},
	{
		metier: 'rssi',
		libelle: 'RSSI',
		profil:
			"RSSI. Veille sur les menaces, les vulnérabilités exploitées et la conformité.\n\nAxes de veille pertinents :\n- menaces : campagnes actives, incidents.\n- conformite : ce que la loi impose à la sécurité.",
		stack: [],
		securite: 'exploitant',
		axes: [
			{ slug: 'menaces', libelle: 'Menaces', description: 'campagnes actives et incidents' },
			{ slug: 'conformite', libelle: 'Conformité', description: 'obligations légales de sécurité' }
		],
		categories: ['1 - Alertes et avis CERT-FR ANSSI', 'Cybersécurité', 'Réglementaire']
	}
];

/**
 * Un MP3 silencieux et valide : des trames MPEG-1 Layer III à 128 kbit/s, 44,1 kHz, dont
 * le contenu nul se décode en silence. Assez pour qu'un lecteur avance dans le fichier.
 * @param {number} secondes
 * @returns {Uint8Array}
 */
export function mp3Silencieux(secondes) {
	const TAILLE_TRAME = 417;
	const trames = Math.ceil((secondes * 44100) / 1152);
	const octets = new Uint8Array(trames * TAILLE_TRAME);
	for (let i = 0; i < trames; i++) {
		octets.set([0xff, 0xfb, 0x90, 0x64], i * TAILLE_TRAME);
	}
	return octets;
}

/**
 * @param {number} statut
 * @param {unknown} [corps]
 */
function json(statut, corps) {
	if (statut === 204) return new Response(null, { status: 204 });
	return new Response(JSON.stringify(corps), {
		status: statut,
		headers: { 'content-type': 'application/json' }
	});
}

/** @param {number} statut @param {string} message @param {string | null} [champ] */
const erreur = (statut, message, champ = null) => json(statut, champ ? { erreur: message, champ } : { erreur: message });

export class FausseApi {
	/** @type {Map<string, ProfilStocke>} */
	profils = new Map();
	/** @type {Map<string, JourneeStockee[]>} */
	journees = new Map();
	/** Les requêtes reçues, pour que les tests vérifient ce qui est parti. @type {Request[]} */
	requetes = [];
	/** Ajoute deux journées d'audio à chaque profil créé : utile en développement. */
	journeesDeDemo = false;
	/** Ce que `GET /api/v1/gabarits` rend ; un test peut le remplacer. @type {GabaritStocke[]} */
	gabarits = GABARITS_DEMO;
	/** Le catalogue des catégories ; `null`, il est ouvert : tout est suivi, rien n'est
	 * proposé ni vérifié. @type {CategorieStockeeCatalogue[] | null} */
	catalogue = CATALOGUE_DEMO;

	/** @param {string} jeton */
	constructor(jeton) {
		this.jeton = jeton;
		this.traiter = this.traiter.bind(this);
	}

	/**
	 * La signature de `fetch`, pour être injectée telle quelle dans le client.
	 * @param {string | URL | Request} entree
	 * @param {RequestInit} [init]
	 * @returns {Promise<Response>}
	 */
	async traiter(entree, init) {
		const requete = new Request(entree, init);
		this.requetes.push(requete.clone());
		if (requete.headers.get('authorization') !== `Bearer ${this.jeton}`) {
			return erreur(401, 'jeton invalide');
		}
		const morceaux = new URL(requete.url).pathname.split('/').filter(Boolean).map(decodeURIComponent);
		if (morceaux[0] === 'api' && morceaux[1] === 'v1' && morceaux[2] === 'passage' && morceaux.length === 3) {
			if (requete.method !== 'GET') return erreur(405, 'méthode non prise en charge');
			return json(200, { heure: HEURE_PASSAGE, fuseau: FUSEAU_PASSAGE, prochain: prochainPassage(new Date()) });
		}
		if (morceaux[0] === 'api' && morceaux[1] === 'v1' && morceaux[2] === 'gabarits' && morceaux.length === 3) {
			if (requete.method !== 'GET') return erreur(405, 'méthode non prise en charge');
			return json(200, this.gabarits);
		}
		if (morceaux[0] !== 'api' || morceaux[1] !== 'v1' || morceaux[2] !== 'profils') {
			return erreur(404, 'route inconnue');
		}
		const [, , , username, sous, date, quoi, nom] = morceaux;
		const methode = requete.method;

		if (username === undefined) {
			if (methode === 'GET') return json(200, [...this.profils.values()].map(resume));
			if (methode === 'POST') return this.#creer(await lireJson(requete));
		} else if (sous === undefined) {
			const profil = this.profils.get(username);
			if (!profil) return erreur(404, `profil inconnu : ${username}`);
			if (methode === 'GET') return json(200, profil);
			if (methode === 'PUT') return this.#modifier(profil, await lireJson(requete));
			if (methode === 'DELETE') {
				this.profils.delete(username);
				this.journees.delete(username);
				return json(204);
			}
		} else if (sous === 'categories' && date === undefined) {
			// Comme l'API : le profil n'a pas à exister, seul le nom doit être valide.
			if (!MOTIF_USERNAME.test(username)) return erreur(404, `profil inconnu : ${username}`);
			if (methode !== 'GET') return erreur(405, 'méthode non prise en charge');
			return json(200, {
				ouvert: this.catalogue === null,
				categories: this.#proposables(username).map(({ libelle, description, proprietaires }) => ({
					libelle,
					description,
					privee: proprietaires.length > 0
				}))
			});
		} else if (sous === 'journees' && methode === 'GET') {
			if (!this.profils.has(username)) return erreur(404, `profil inconnu : ${username}`);
			const journees = this.journees.get(username) ?? [];
			if (date === undefined) {
				return json(
					200,
					[...journees]
						.sort((a, b) => b.date.localeCompare(a.date))
						.map((j) => ({
							date: j.date,
							audios: j.audios.map((a) => ({ nom: a.nom, taille: a.octets.length }))
						}))
				);
			}
			const journee = journees.find((j) => j.date === date);
			if (quoi === undefined) {
				if (!journee) return erreur(404, 'Journée introuvable.');
				return json(200, contenuDe(journee));
			}
			const audio = journee?.audios.find((a) => a.nom === nom);
			if (quoi !== 'audios' || !audio) return erreur(404, 'audio introuvable');
			return servirAudio(audio.octets, requete.headers.get('range'));
		}
		return erreur(405, 'méthode non prise en charge');
	}

	/**
	 * @param {string} username
	 * @param {string} date
	 * @param {string} nom
	 * @param {Uint8Array} octets
	 */
	ajouterAudio(username, date, nom, octets) {
		this.#journee(username, date).audios.push({ nom, octets });
	}

	/**
	 * Le contenu d'une journée, comme ses journaux le donneraient. Crée la journée même sans
	 * audio : une journée sans article est listée, comme le fait l'API.
	 * @param {string} username
	 * @param {string} date
	 * @param {ContenuStocke} contenu
	 */
	ajouterContenu(username, date, contenu) {
		this.#journee(username, date).contenu = contenu;
	}

	/** @param {string} username @param {string} date */
	#journee(username, date) {
		const journees = this.journees.get(username) ?? [];
		let journee = journees.find((j) => j.date === date);
		if (!journee) {
			journee = { date, audios: [] };
			journees.push(journee);
		}
		this.journees.set(username, journees);
		return journee;
	}

	/** @param {any} corps */
	#creer(corps) {
		if (!corps || typeof corps.username !== 'string' || !MOTIF_USERNAME.test(corps.username)) {
			return erreur(422, 'username invalide');
		}
		if (this.profils.has(corps.username)) return erreur(409, `username déjà pris : ${corps.username}`);
		const invalide = this.#valider(corps, corps.username);
		if (invalide) return erreur(422, invalide.message, invalide.champ);
		/** @type {ProfilStocke} */
		const profil = {
			// Attribué ici et jamais lu dans le corps : un `id` envoyé par le client est ignoré.
			id: crypto.randomUUID(),
			username: corps.username,
			profil: corps.profil,
			stack: corps.stack ?? [],
			email: corps.email ?? [],
			prenom: corps.prenom ?? '',
			securite: corps.securite ?? 'exploitant',
			...reglages(corps),
			modifie_le: new Date().toISOString()
		};
		this.profils.set(profil.username, profil);
		if (this.journeesDeDemo) {
			const hier = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
			const avantHier = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);
			const troisJours = new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 10);
			this.ajouterAudio(profil.username, avantHier, 'cyber.mp3', mp3Silencieux(20));
			this.ajouterAudio(profil.username, avantHier, 'stack.mp3', mp3Silencieux(15));
			this.ajouterContenu(profil.username, avantHier, CONTENU_DEMO_CATEGORIES);
			this.ajouterAudio(profil.username, hier, 'journee.mp3', mp3Silencieux(60));
			this.ajouterContenu(profil.username, hier, CONTENU_DEMO_JOURNEE);
			this.ajouterContenu(profil.username, troisJours, {});
		}
		return json(201, profil);
	}

	/** @param {ProfilStocke} profil @param {any} corps */
	#modifier(profil, corps) {
		const invalide = this.#valider(corps, profil.username);
		if (invalide) return erreur(422, invalide.message, invalide.champ);
		// Remplacement complet, comme l'API : des axes ou catégories absents du corps
		// disparaissent du profil.
		delete profil.axes;
		delete profil.categories;
		Object.assign(profil, {
			profil: corps.profil,
			stack: corps.stack ?? [],
			email: corps.email ?? [],
			prenom: corps.prenom ?? '',
			securite: corps.securite ?? 'exploitant',
			...reglages(corps),
			modifie_le: new Date().toISOString()
		});
		return json(200, profil);
	}

	/** Les catégories que `username` peut suivre : publiques, ou privées dont il est
	 * propriétaire. @param {string} username */
	#proposables(username) {
		return (this.catalogue ?? []).filter(
			(categorie) => !categorie.proprietaires.length || categorie.proprietaires.includes(username)
		);
	}

	/** Les règles du document, puis le catalogue : une catégorie privée d'un autre est
	 * refusée comme une inconnue, comme le fait l'API. @param {any} corps @param {string} username */
	#valider(corps, username) {
		const invalide = valider(corps);
		if (invalide || this.catalogue === null || !Array.isArray(corps.categories)) return invalide;
		const permises = new Set(this.#proposables(username).map((categorie) => categorie.libelle));
		const refusee = corps.categories.find((/** @type {any} */ libelle) => !permises.has(String(libelle)));
		if (refusee === undefined) return null;
		return { champ: 'categories', message: `categories : catégorie « ${refusee} » inconnue du catalogue` };
	}
}

/**
 * Les axes et catégories déclarés par un corps. Une liste vide vaut une clé absente, comme
 * dans l'API : le profil revient alors aux réglages par défaut.
 * @param {any} corps
 * @returns {{ axes?: AxeStocke[], categories?: string[] }}
 */
function reglages(corps) {
	/** @type {{ axes?: AxeStocke[], categories?: string[] }} */
	const declares = {};
	if (Array.isArray(corps.axes) && corps.axes.length) declares.axes = corps.axes;
	if (Array.isArray(corps.categories) && corps.categories.length) declares.categories = corps.categories;
	return declares;
}

/**
 * La réponse de `GET …/journees/{date}` : ce qui a été stocké, complété comme l'API le ferait.
 * @param {JourneeStockee} journee
 */
function contenuDe(journee) {
	const contenu = journee.contenu ?? {};
	const categories = contenu.categories ?? [];
	const enCours = contenu.en_cours ?? false;
	return {
		date: journee.date,
		audios: journee.audios.map((a) => ({ nom: a.nom, taille: a.octets.length })),
		ecoute: contenu.ecoute ?? null,
		racontees: contenu.racontees ?? categories.filter((c) => c.racontee).length,
		montage: contenu.montage ?? null,
		raison:
			contenu.raison ??
			(enCours || categories.length ? null : `Aucun article trouvé pour le ${journee.date}.`),
		en_cours: enCours,
		categories
	};
}

/**
 * Le prochain 04:00 à Paris, en ISO 8601 avec son décalage, comme `DailySchedule.next_run`.
 * @param {Date} maintenant
 */
function prochainPassage(maintenant) {
	const jourA = new Intl.DateTimeFormat('en-CA', { timeZone: FUSEAU_PASSAGE });
	for (let jours = 0; jours <= 2; jours++) {
		const jour = jourA.format(new Date(maintenant.getTime() + jours * 86_400_000));
		const commeUtc = Date.parse(`${jour}T${HEURE_PASSAGE}:00Z`);
		const minutes = decalageMinutes(new Date(commeUtc));
		const instant = commeUtc - minutes * 60_000;
		if (instant > maintenant.getTime()) {
			const signe = minutes < 0 ? '-' : '+';
			const absolu = Math.abs(minutes);
			const hh = String(Math.floor(absolu / 60)).padStart(2, '0');
			const mm = String(absolu % 60).padStart(2, '0');
			return `${jour}T${HEURE_PASSAGE}:00${signe}${hh}:${mm}`;
		}
	}
	throw new Error('passage introuvable');
}

/** Le décalage du fuseau du passage à cet instant, en minutes. @param {Date} instant */
function decalageMinutes(instant) {
	const parties = Object.fromEntries(
		new Intl.DateTimeFormat('en-US', {
			timeZone: FUSEAU_PASSAGE,
			hourCycle: 'h23',
			year: 'numeric',
			month: 'numeric',
			day: 'numeric',
			hour: 'numeric',
			minute: 'numeric'
		})
			.formatToParts(instant)
			.map((p) => [p.type, p.value])
	);
	const local = Date.UTC(+parties.year, +parties.month - 1, +parties.day, +parties.hour, +parties.minute);
	return Math.round((local - Math.floor(instant.getTime() / 60_000) * 60_000) / 60_000);
}

/** @type {ContenuStocke} */
const CONTENU_DEMO_CATEGORIES = {
	ecoute: '1 min',
	racontees: 2,
	categories: [
		{
			categorie: 'Cybersécurité',
			racontee: true,
			resume:
				"Une faille critique touche un reverse proxy très répandu : la mise à jour corrige une élévation de privilèges.\n\nLes éditeurs recommandent de l'appliquer sans attendre la prochaine fenêtre de maintenance.",
			audio: 'cyber.mp3',
			ecoute: "moins d'1 min",
			articles: [
				{ titre: 'Faille critique dans un reverse proxy', source: 'CERT-FR', url: 'https://www.cert.ssi.gouv.fr/' }
			],
			a_surveiller: [
				{ titre: 'Un correctif attendu pour un IdP', source: 'Flux sécurité', url: 'https://example.com/idp' }
			]
		},
		{
			categorie: 'Stack',
			racontee: true,
			resume: 'Une version majeure sort, avec une rupture de compatibilité sur la configuration.',
			audio: 'stack.mp3',
			ecoute: "moins d'1 min",
			articles: [{ titre: 'Version 4.0 publiée', source: 'Blog du projet', url: 'https://example.com/v4' }],
			a_surveiller: []
		}
	]
};

/** @type {ContenuStocke} */
const CONTENU_DEMO_JOURNEE = {
	ecoute: '1 min',
	racontees: 1,
	montage: { audio: 'journee.mp3', ecoute: '1 min' },
	categories: [
		{
			categorie: 'Réglementaire',
			racontee: true,
			resume: "Un nouveau texte encadre la conservation des journaux d'accès.",
			audio: null,
			ecoute: null,
			articles: [{ titre: 'Le texte au Journal officiel', source: 'Légifrance', url: 'https://www.legifrance.gouv.fr/' }],
			a_surveiller: []
		}
	]
};

/** @param {ProfilStocke} p */
function resume(p) {
	return { id: p.id, username: p.username, prenom: p.prenom, email: p.email, modifie_le: p.modifie_le };
}

/**
 * Les règles de `rssresume/profil.py`, en plus court : la clé fautive, et le message.
 * @param {any} corps
 * @returns {{ champ: string | null, message: string } | null}
 */
function valider(corps) {
	if (!corps || typeof corps !== 'object' || Array.isArray(corps)) {
		return { champ: null, message: 'un profil est un objet JSON' };
	}
	if (typeof corps.profil !== 'string' || !corps.profil.trim()) {
		return { champ: 'profil', message: 'profil : un texte non vide est exigé' };
	}
	if (corps.stack !== undefined && !Array.isArray(corps.stack)) {
		return { champ: 'stack', message: 'stack : une liste est attendue' };
	}
	if (corps.email !== undefined) {
		if (!Array.isArray(corps.email)) return { champ: 'email', message: 'email : une liste est attendue' };
		for (const adresse of corps.email) {
			if (typeof adresse !== 'string' || !/^[^\s@]+@[^\s@]+$/.test(adresse)) {
				return { champ: 'email', message: `email : adresse invalide (${String(adresse)})` };
			}
		}
	}
	if (corps.prenom !== undefined && typeof corps.prenom !== 'string') {
		return { champ: 'prenom', message: 'prenom : un texte est attendu' };
	}
	if (corps.securite !== undefined && !['exploitant', 'decideur', 'curieux'].includes(corps.securite)) {
		return { champ: 'securite', message: 'securite : exploitant, decideur ou curieux est attendu' };
	}
	return null;
}

/** @param {Request} requete */
async function lireJson(requete) {
	try {
		return await requete.json();
	} catch {
		return null;
	}
}

/**
 * `Range: bytes=a-b`, `bytes=a-` ou `bytes=-n` ; une seule plage, comme les lecteurs audio.
 * @param {Uint8Array} octets
 * @param {string | null} range
 */
function servirAudio(octets, range) {
	const taille = octets.length;
	const communs = { 'content-type': 'audio/mpeg', 'accept-ranges': 'bytes' };
	if (!range) {
		return new Response(/** @type {BodyInit} */ (octets), {
			status: 200,
			headers: { ...communs, 'content-length': String(taille) }
		});
	}
	const plage = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
	let debut = NaN;
	let fin = NaN;
	if (plage && (plage[1] || plage[2])) {
		if (plage[1]) {
			debut = Number(plage[1]);
			fin = plage[2] ? Math.min(Number(plage[2]), taille - 1) : taille - 1;
		} else {
			debut = Math.max(0, taille - Number(plage[2]));
			fin = taille - 1;
		}
	}
	if (!(debut <= fin) || debut >= taille) {
		return new Response(null, { status: 416, headers: { 'content-range': `bytes */${taille}` } });
	}
	return new Response(octets.slice(debut, fin + 1), {
		status: 206,
		headers: {
			...communs,
			'content-length': String(fin - debut + 1),
			'content-range': `bytes ${debut}-${fin}/${taille}`
		}
	});
}
