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
 * @typedef {{ id: string, username: string, profil: string, stack: ComposantStack[], email: string[], prenom: string, modifie_le: string }} ProfilStocke
 * @typedef {{ date: string, audios: { nom: string, octets: Uint8Array }[] }} JourneeStockee
 */

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

/** @param {number} statut @param {string} message */
const erreur = (statut, message) => json(statut, { erreur: message });

export class FausseApi {
	/** @type {Map<string, ProfilStocke>} */
	profils = new Map();
	/** @type {Map<string, JourneeStockee[]>} */
	journees = new Map();
	/** Les requêtes reçues, pour que les tests vérifient ce qui est parti. @type {Request[]} */
	requetes = [];
	/** Ajoute deux journées d'audio à chaque profil créé : utile en développement. */
	journeesDeDemo = false;

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
			const audio = journees.find((j) => j.date === date)?.audios.find((a) => a.nom === nom);
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
		const journees = this.journees.get(username) ?? [];
		let journee = journees.find((j) => j.date === date);
		if (!journee) {
			journee = { date, audios: [] };
			journees.push(journee);
		}
		journee.audios.push({ nom, octets });
		this.journees.set(username, journees);
	}

	/** @param {any} corps */
	#creer(corps) {
		if (!corps || typeof corps.username !== 'string' || !MOTIF_USERNAME.test(corps.username)) {
			return erreur(422, 'username invalide');
		}
		if (this.profils.has(corps.username)) return erreur(409, `username déjà pris : ${corps.username}`);
		const invalide = valider(corps);
		if (invalide) return erreur(422, invalide);
		/** @type {ProfilStocke} */
		const profil = {
			// Attribué ici et jamais lu dans le corps : un `id` envoyé par le client est ignoré.
			id: crypto.randomUUID(),
			username: corps.username,
			profil: corps.profil,
			stack: corps.stack ?? [],
			email: corps.email ?? [],
			prenom: corps.prenom ?? '',
			modifie_le: new Date().toISOString()
		};
		this.profils.set(profil.username, profil);
		if (this.journeesDeDemo) {
			const hier = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
			const avantHier = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);
			this.ajouterAudio(profil.username, avantHier, 'cyber.mp3', mp3Silencieux(20));
			this.ajouterAudio(profil.username, avantHier, 'stack.mp3', mp3Silencieux(15));
			this.ajouterAudio(profil.username, hier, 'journee.mp3', mp3Silencieux(60));
		}
		return json(201, profil);
	}

	/** @param {ProfilStocke} profil @param {any} corps */
	#modifier(profil, corps) {
		const invalide = valider(corps);
		if (invalide) return erreur(422, invalide);
		Object.assign(profil, {
			profil: corps.profil,
			stack: corps.stack ?? [],
			email: corps.email ?? [],
			prenom: corps.prenom ?? '',
			modifie_le: new Date().toISOString()
		});
		return json(200, profil);
	}
}

/** @param {ProfilStocke} p */
function resume(p) {
	return { id: p.id, username: p.username, prenom: p.prenom, email: p.email, modifie_le: p.modifie_le };
}

/** Les règles de `rssresume/profil.py`, en plus court. @param {any} corps */
function valider(corps) {
	if (!corps || typeof corps.profil !== 'string' || !corps.profil.trim()) {
		return 'profil : un texte non vide est exigé';
	}
	if (corps.stack !== undefined && !Array.isArray(corps.stack)) return 'stack : une liste est attendue';
	if (corps.email !== undefined) {
		if (!Array.isArray(corps.email)) return 'email : une liste est attendue';
		for (const adresse of corps.email) {
			if (typeof adresse !== 'string' || !/^[^\s@]+@[^\s@]+$/.test(adresse)) {
				return `email : adresse invalide (${String(adresse)})`;
			}
		}
	}
	if (corps.prenom !== undefined && typeof corps.prenom !== 'string') return 'prenom : un texte est attendu';
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
