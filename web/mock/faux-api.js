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

/** Le refus de `rssresume/api/routes.py`, le même quelle qu'en soit la raison. */
const LIEN_DESABONNEMENT_INVALIDE = 'Lien de désabonnement invalide ou déjà utilisé.';
const LIEN_RETOUR_INVALIDE = 'Lien de vote invalide.';
/** Les bornes de `rssresume/retours.py`. */
const LONGUEUR_MAX_COMMENTAIRE = 2000;
const LIMITE_LISTE_RETOURS = 200;

/**
 * @typedef {{ username: string | null, jour: string, avis: 'utile' | 'pas_utile', commentaire: string, vote_le: string }} RetourStocke
 */

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
	/** Les jetons de désabonnement déclarés, et le profil que chacun vise. @type {Map<string, string>} */
	desabonnements = new Map();
	/** Les jetons de vote déclarés, et la journée que chacun vise. @type {Map<string, { username: string, jour: string }>} */
	liensRetour = new Map();
	/** Les votes, un par profil et par journée (clé `username|jour`). @type {Map<string, RetourStocke & { rang: number }>} */
	retours = new Map();
	#rangRetour = 0;

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
		if (morceaux[0] === 'api' && morceaux[1] === 'v1' && morceaux[2] === 'desabonnements') {
			const lecture = morceaux[3] === 'lecture' && morceaux.length === 4;
			if (!lecture && morceaux.length !== 3) return erreur(404, 'route inconnue');
			if (requete.method !== 'POST') return erreur(405, 'méthode non prise en charge');
			return this.#desabonner(await lireJson(requete), lecture);
		}
		if (morceaux[0] === 'api' && morceaux[1] === 'v1' && morceaux[2] === 'retours') {
			const lecture = morceaux[3] === 'lecture' && morceaux.length === 4;
			if (!lecture && morceaux.length !== 3) return erreur(404, 'route inconnue');
			if (!lecture && requete.method === 'GET') {
				return json(
					200,
					[...this.retours.values()]
						.sort((a, b) => b.vote_le.localeCompare(a.vote_le) || b.rang - a.rang)
						.slice(0, LIMITE_LISTE_RETOURS)
						.map(sansRang)
				);
			}
			if (requete.method !== 'POST') return erreur(405, 'méthode non prise en charge');
			return this.#voterParLien(await lireJson(requete), lecture);
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
		} else if (sous === 'journees' && date !== undefined && quoi === 'retour' && nom === undefined) {
			// Comme l'API : la journée n'a pas à exister sur le disque, seule la date doit être valide.
			if (!this.profils.has(username) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
				return erreur(404, 'Journée introuvable.');
			}
			if (methode === 'GET') {
				const retour = this.retours.get(`${username}|${date}`);
				return retour ? json(200, sansRang(retour)) : erreur(404, 'Aucun retour pour cette journée.');
			}
			if (methode === 'PUT') return this.#enregistrerRetour(username, date, await lireJson(requete));
			return erreur(405, 'méthode non prise en charge');
		} else if (sous === 'journees' && methode === 'GET') {
			if (!this.profils.has(username)) {
				if (this.journeesDeDemo && MOTIF_USERNAME.test(username)) this.#semerProfilDemo(username);
				else return erreur(404, `profil inconnu : ${username}`);
			}
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

	/**
	 * Un jeton de désabonnement valable pour `username`. L'API le vérifie par sa signature ;
	 * ici, il suffit qu'il ait été déclaré, et il cesse de valoir une fois servi — ou dès que
	 * le profil n'a plus de destinataire, comme le jeton lié aux adresses de l'API.
	 * @param {string} jeton
	 * @param {string} username
	 */
	ajouterDesabonnement(jeton, username) {
		this.desabonnements.set(jeton, username);
	}

	/**
	 * Un jeton de vote valable pour la journée `jour` de `username`. L'API le vérifie par sa
	 * signature ; ici, il suffit qu'il ait été déclaré. Il vaut tant que le profil existe.
	 * @param {string} jeton
	 * @param {string} username
	 * @param {string} jour
	 */
	ajouterLienRetour(jeton, username, jour) {
		this.liensRetour.set(jeton, { username, jour });
	}

	/** @param {any} corps @param {boolean} lecture */
	#voterParLien(corps, lecture) {
		const jeton = corps && typeof corps.jeton === 'string' ? corps.jeton : null;
		const vise = jeton === null ? undefined : this.liensRetour.get(jeton);
		if (!vise || !this.profils.has(vise.username)) return erreur(404, LIEN_RETOUR_INVALIDE);
		if (lecture) {
			const retour = this.retours.get(`${vise.username}|${vise.jour}`);
			return json(200, { username: vise.username, jour: vise.jour, retour: retour ? sansRang(retour) : null });
		}
		const reponse = this.#enregistrerRetour(vise.username, vise.jour, corps);
		if (!reponse.ok) return reponse;
		const retour = /** @type {RetourStocke & { rang: number }} */ (this.retours.get(`${vise.username}|${vise.jour}`));
		return json(200, { username: vise.username, jour: vise.jour, retour: sansRang(retour) });
	}

	/** Les règles de `Retour.saisi`, puis le remplacement du vote de la journée.
	 * @param {string} username @param {string} jour @param {any} corps */
	#enregistrerRetour(username, jour, corps) {
		const avis = corps?.avis;
		if (avis !== 'utile' && avis !== 'pas_utile') {
			return erreur(422, 'avis : « utile » ou « pas_utile » est attendu.', 'avis');
		}
		const brut = corps.commentaire ?? '';
		if (typeof brut !== 'string') return erreur(422, 'commentaire : un texte est attendu.', 'commentaire');
		const commentaire = brut.replace(/\r\n?/g, '\n').trim();
		if ([...commentaire].length > LONGUEUR_MAX_COMMENTAIRE) {
			return erreur(422, `commentaire : ${LONGUEUR_MAX_COMMENTAIRE} caractères au plus.`, 'commentaire');
		}
		const retour = { username, jour, avis, commentaire, vote_le: new Date().toISOString(), rang: ++this.#rangRetour };
		this.retours.set(`${username}|${jour}`, retour);
		return json(200, sansRang(retour));
	}

	/** @param {any} corps @param {boolean} lecture */
	#desabonner(corps, lecture) {
		const jeton = corps && typeof corps.jeton === 'string' ? corps.jeton : null;
		const username = jeton === null ? undefined : this.desabonnements.get(jeton);
		const profil = username === undefined ? undefined : this.profils.get(username);
		if (!profil || !profil.email.length) return erreur(404, LIEN_DESABONNEMENT_INVALIDE);
		if (lecture) return json(200, { username: profil.username, destinataires: profil.email.length });
		profil.email = [];
		profil.modifie_le = new Date().toISOString();
		this.desabonnements.delete(/** @type {string} */ (jeton));
		return json(200, { username: profil.username });
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
		if (this.journeesDeDemo) this.#ajouterJourneesDemo(profil.username);
		return json(201, profil);
	}

	/** @param {string} username */
	#semerProfilDemo(username) {
		/** @type {ProfilStocke} */
		const profil = {
			id: crypto.randomUUID(),
			username,
			profil: "Profil de démonstration généré automatiquement pour les maquettes du site.",
			stack: [],
			email: [`${username}@example.com`],
			prenom: '',
			securite: 'exploitant',
			modifie_le: new Date().toISOString()
		};
		this.profils.set(username, profil);
		this.#ajouterJourneesDemo(username);
	}

	/** @param {string} username */
	#ajouterJourneesDemo(username) {
		if ((this.journees.get(username) ?? []).length) return;
		for (let index = 0; index < 7; index++) {
			const date = new Date(Date.now() - (index + 1) * 86_400_000).toISOString().slice(0, 10);
			this.ajouterAudio(username, date, 'journee.mp3', mp3Silencieux(24 + (index % 3) * 6));
			this.ajouterContenu(username, date, contenuDemoJournee(index));
		}
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

const DUREES_DEMO = ['8 min', '7 min', '6 min', '10 min', '9 min', '5 min', '11 min'];
const CATEGORIES_DEMO = ['Cybersécurité', 'Cloud & infra', 'Réglementaire', 'Tech généraliste', 'Souveraineté numérique'];
const JOURNEES_DEMO = [
	{ ecoute: '8 min', categories: 4, articles: 5 },
	{ ecoute: '7 min', categories: 3, articles: 4 },
	{ ecoute: '6 min', categories: 2, articles: 3 },
	{ ecoute: '10 min', categories: 4, articles: 6 },
	{ ecoute: '9 min', categories: 3, articles: 5 },
	{ ecoute: '5 min', categories: 2, articles: 2 },
	{ ecoute: '11 min', categories: 4, articles: 7 }
];

/** @param {number} index @returns {ContenuStocke} */
function contenuDemoJournee(index) {
	const fiche = JOURNEES_DEMO[index % JOURNEES_DEMO.length];
	const nombreCategories = fiche.categories;
	const ecoute = fiche.ecoute;
	const baseArticles = Math.floor(fiche.articles / nombreCategories);
	let resteArticles = fiche.articles % nombreCategories;
	const categories = Array.from({ length: nombreCategories }, (_, rang) => {
		const articlesAvoir = baseArticles + (resteArticles > 0 ? 1 : 0);
		resteArticles = Math.max(0, resteArticles - 1);
		return {
			categorie: CATEGORIES_DEMO[(index + rang) % CATEGORIES_DEMO.length],
			racontee: true,
			resume: 'Résumé de démonstration pour la maquette du tableau de bord.',
			audio: null,
			ecoute: null,
			articles: Array.from({ length: articlesAvoir }, (_, article) => ({
				titre: `Article ${article + 1}`,
				source: 'Flux demo',
				url: 'https://example.com/article'
			})),
			a_surveiller: []
		};
	});
	return {
		ecoute,
		racontees: nombreCategories,
		montage: { audio: 'journee.mp3', ecoute },
		categories
	};
}

/** Le retour tel que l'API le rend, sans le rang qui ne sert qu'à départager deux votes de
 * la même milliseconde. @param {RetourStocke & { rang: number }} retour @returns {RetourStocke} */
function sansRang({ rang, ...retour }) {
	return retour;
}

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
