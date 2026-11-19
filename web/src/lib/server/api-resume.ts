/**
 * Le client de l'API de résumé : le seul endroit du site qui connaît ses chemins et son jeton.
 *
 * Le contrat est écrit dans `web/API.md`. Le tenir dans une seule classe, c'est pouvoir le
 * relire d'un coup d'œil quand l'API change, et c'est surtout s'assurer que le jeton ne
 * part que d'ici : le module est sous `server/`, que SvelteKit refuse d'envoyer au
 * navigateur.
 */

import type { Profil, ProfilSaisi, ResumeProfil } from '#lib/profil.js';

export interface AudioJournee {
	nom: string;
	taille: number;
}

export interface Journee {
	date: string;
	audios: AudioJournee[];
}

/** Une réponse d'erreur de l'API, ou son absence.
 *
 * `statut` vaut 0 quand l'API n'a pas répondu du tout : la page doit pouvoir dire « le
 * service est indisponible » sans confondre ce cas avec un 404. */
export class ErreurApi extends Error {
	constructor(
		readonly statut: number,
		message: string
	) {
		super(message);
		this.name = 'ErreurApi';
	}

	get introuvable(): boolean {
		return this.statut === 404;
	}
}

/** Les seuls champs qu'un corps POST/PUT porte. Recopiés un à un plutôt qu'étalés : un
 * `Profil` complet passé par erreur n'enverrait ni `id` ni `modifie_le`, que l'API seule
 * attribue. */
function corpsProfil(saisie: ProfilSaisi): ProfilSaisi {
	return { profil: saisie.profil, stack: saisie.stack, email: saisie.email, prenom: saisie.prenom };
}

export interface OptionsClient {
	baseUrl: string;
	jeton: string;
	/** Injecté pour les tests ; le `fetch` global sinon. */
	fetch?: typeof fetch;
	/** Délai des appels JSON. L'audio n'en a pas : un flux long n'est pas une panne. */
	delaiMs?: number;
}

export class ClientApiResume {
	readonly #base: string;
	readonly #jeton: string;
	readonly #fetch: typeof fetch;
	readonly #delaiMs: number;

	constructor(options: OptionsClient) {
		this.#base = options.baseUrl.replace(/\/+$/, '');
		this.#jeton = options.jeton;
		this.#fetch = options.fetch ?? fetch;
		this.#delaiMs = options.delaiMs ?? 10_000;
	}

	listerProfils(): Promise<ResumeProfil[]> {
		return this.#json('GET', '/api/v1/profils');
	}

	creerProfil(username: string, saisie: ProfilSaisi): Promise<Profil> {
		return this.#json('POST', '/api/v1/profils', { username, ...corpsProfil(saisie) });
	}

	lireProfil(username: string): Promise<Profil> {
		return this.#json('GET', this.#profil(username));
	}

	modifierProfil(username: string, saisie: ProfilSaisi): Promise<Profil> {
		return this.#json('PUT', this.#profil(username), corpsProfil(saisie));
	}

	async supprimerProfil(username: string): Promise<void> {
		await this.#json('DELETE', this.#profil(username));
	}

	listerJournees(username: string): Promise<Journee[]> {
		return this.#json('GET', `${this.#profil(username)}/journees`);
	}

	/** Le flux audio brut, statut et en-têtes compris : le relais les recopie.
	 *
	 * Rend la `Response` plutôt qu'un flux pour que 200, 206 et 416 passent intacts ;
	 * seules les erreurs JSON de l'API (404 surtout) deviennent des `ErreurApi`. */
	async audio(
		username: string,
		date: string,
		nom: string,
		options: { range?: string | null; signal?: AbortSignal } = {}
	): Promise<Response> {
		const chemin =
			`${this.#profil(username)}/journees/${encodeURIComponent(date)}` +
			`/audios/${encodeURIComponent(nom)}`;
		const entetes: Record<string, string> = {};
		if (options.range) entetes.Range = options.range;
		const reponse = await this.#appeler('GET', chemin, { entetes, signal: options.signal });
		if (reponse.status === 200 || reponse.status === 206 || reponse.status === 416) {
			return reponse;
		}
		throw await this.#erreur(reponse);
	}

	#profil(username: string): string {
		return `/api/v1/profils/${encodeURIComponent(username)}`;
	}

	async #json<T>(methode: string, chemin: string, corps?: unknown): Promise<T> {
		const entetes: Record<string, string> = { Accept: 'application/json' };
		let texte: string | undefined;
		if (corps !== undefined) {
			entetes['Content-Type'] = 'application/json';
			texte = JSON.stringify(corps);
		}
		const reponse = await this.#appeler(methode, chemin, {
			entetes,
			corps: texte,
			signal: AbortSignal.timeout(this.#delaiMs)
		});
		if (!reponse.ok) throw await this.#erreur(reponse);
		if (reponse.status === 204) return undefined as T;
		return (await reponse.json()) as T;
	}

	async #appeler(
		methode: string,
		chemin: string,
		options: { entetes: Record<string, string>; corps?: string; signal?: AbortSignal }
	): Promise<Response> {
		if (!this.#base) {
			throw new ErreurApi(0, "RSSRESUME_API_URL n'est pas renseignée : l'API de résumé est injoignable.");
		}
		try {
			return await this.#fetch(this.#base + chemin, {
				method: methode,
				headers: { ...options.entetes, Authorization: `Bearer ${this.#jeton}` },
				body: options.corps,
				signal: options.signal
			});
		} catch (cause) {
			// Le message d'origine peut contenir l'URL interne : il va au journal, pas à la page.
			console.error(`API de résumé injoignable (${methode} ${chemin}) :`, cause);
			throw new ErreurApi(0, 'Le service de résumé est momentanément indisponible.');
		}
	}

	async #erreur(reponse: Response): Promise<ErreurApi> {
		let message = `Le service de résumé a répondu ${reponse.status}.`;
		try {
			const corps = (await reponse.json()) as { erreur?: unknown };
			if (typeof corps.erreur === 'string' && corps.erreur) message = corps.erreur;
		} catch {
			// Corps absent ou non JSON : le message générique suffit.
		}
		if (reponse.status === 401) {
			// Un 401 est une erreur de déploiement (jeton faux), pas une faute de la personne.
			console.error('API de résumé : jeton refusé (401). Vérifier RSSRESUME_API_TOKEN.');
			message = 'Le service de résumé refuse la connexion du site.';
		}
		return new ErreurApi(reponse.status, message);
	}
}
