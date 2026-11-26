/**
 * Le client de l'API de résumé : le seul endroit du site qui connaît ses chemins et son jeton.
 *
 * Le contrat est écrit dans `web/API.md`. Le tenir dans une seule classe, c'est pouvoir le
 * relire d'un coup d'œil quand l'API change, et c'est surtout s'assurer que le jeton ne
 * part que d'ici : le module est sous `server/`, que SvelteKit refuse d'envoyer au
 * navigateur.
 */

import type { ContenuJournee, Passage } from '#lib/journee.js';
import type { CategoriesProposees, Gabarit, Profil, ProfilSaisi, ResumeProfil } from '#lib/profil.js';
import type { Avis } from '#lib/retour.js';

export interface AudioJournee {
	nom: string;
	taille: number;
}

export interface Journee {
	date: string;
	audios: AudioJournee[];
}

/** Ce qu'un lien de désabonnement désigne, avant qu'on l'applique. */
export interface DemandeDesabonnement {
	username: string;
	destinataires: number;
}

/** Un vote sur une journée, tel que l'API le garde. `username` est `null` quand le profil a
 * été supprimé depuis : le retour reste. */
export interface Retour {
	username: string | null;
	jour: string;
	avis: Avis;
	commentaire: string;
	vote_le: string | null;
}

/** Ce qu'un lien de vote désigne, et le vote déjà donné sur cette journée. */
export interface LectureRetour {
	username: string;
	jour: string;
	retour: Retour | null;
}

/** Une réponse d'erreur de l'API, ou son absence.
 *
 * `statut` vaut 0 quand l'API n'a pas répondu du tout : la page doit pouvoir dire « le
 * service est indisponible » sans confondre ce cas avec un 404. `champ` nomme la clé du
 * profil refusée quand l'API la connaît : la page affiche le refus sous ce champ. */
export class ErreurApi extends Error {
	constructor(
		readonly statut: number,
		message: string,
		readonly champ: string | null = null
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
 * attribue.
 *
 * En `PUT` (`fusion`), le serveur n'applique que les clés présentes dans le corps, une
 * clé absente garde sa valeur stockée, un `null` explicite remet à son défaut (web/API.md).
 * Le client n'envoie donc que ce qu'il édite : `axes` absent garde ceux du profil, et le
 * `categories: null` de « tout est coché » part tel quel, car omettre la clé ne veut plus
 * dire « tout le catalogue » mais « garder l'abonnement actuel ». En `POST`, `null` reste
 * omis : absent y vaut défaut, comme avant. */
function corpsProfil(saisie: ProfilSaisi, fusion: boolean): ProfilSaisi {
	const corps: ProfilSaisi = {
		profil: saisie.profil,
		stack: saisie.stack,
		email: saisie.email,
		prenom: saisie.prenom,
		securite: saisie.securite
	};
	if (saisie.axes !== undefined) corps.axes = saisie.axes;
	if (fusion) {
		if (saisie.categories !== undefined) corps.categories = saisie.categories;
	} else if (saisie.categories != null) {
		corps.categories = saisie.categories;
	}
	return corps;
}

export interface OptionsClient {
	baseUrl: string;
	jeton: string;
	/** Injecté pour les tests ; le `fetch` global sinon. */
	fetch?: typeof fetch;
	/** Délai des appels JSON. L'audio n'en a pas : un flux long n'est pas une panne. */
	delaiMs?: number;
	/** Durée de vie de la liste des gabarits en mémoire. */
	dureeGabaritsMs?: number;
	/** Injectée pour les tests ; `Date.now` sinon. */
	maintenant?: () => number;
}

export class ClientApiResume {
	readonly #base: string;
	readonly #jeton: string;
	readonly #fetch: typeof fetch;
	readonly #delaiMs: number;
	readonly #dureeGabaritsMs: number;
	readonly #maintenant: () => number;
	#gabarits: { liste: Gabarit[]; expireLe: number } | null = null;

	constructor(options: OptionsClient) {
		this.#base = options.baseUrl.replace(/\/+$/, '');
		this.#jeton = options.jeton;
		this.#fetch = options.fetch ?? fetch;
		this.#delaiMs = options.delaiMs ?? 10_000;
		this.#dureeGabaritsMs = options.dureeGabaritsMs ?? 5 * 60 * 1000;
		this.#maintenant = options.maintenant ?? Date.now;
	}

	listerProfils(): Promise<ResumeProfil[]> {
		return this.#json('GET', '/api/v1/profils');
	}

	creerProfil(username: string, saisie: ProfilSaisi): Promise<Profil> {
		return this.#json('POST', '/api/v1/profils', { username, ...corpsProfil(saisie, false) });
	}

	lireProfil(username: string): Promise<Profil> {
		return this.#json('GET', this.#profil(username));
	}

	modifierProfil(username: string, saisie: ProfilSaisi): Promise<Profil> {
		return this.#json('PUT', this.#profil(username), corpsProfil(saisie, true));
	}

	async supprimerProfil(username: string): Promise<void> {
		await this.#json('DELETE', this.#profil(username));
	}

	listerJournees(username: string): Promise<Journee[]> {
		return this.#json('GET', `${this.#profil(username)}/journees`);
	}

	lireJournee(username: string, date: string): Promise<ContenuJournee> {
		return this.#json('GET', `${this.#profil(username)}/journees/${encodeURIComponent(date)}`);
	}

	lirePassage(): Promise<Passage> {
		return this.#json('GET', '/api/v1/passage');
	}

	/** Les catégories que `username` peut cocher. Pas de cache, contrairement aux gabarits :
	 * la liste dépend de la personne, et seule « Mon profil » la demande. */
	listerCategories(username: string): Promise<CategoriesProposees> {
		return this.#json('GET', `${this.#profil(username)}/categories`);
	}

	/** Ce que le lien de désabonnement viderait, sans rien changer. Le jeton part dans le
	 * corps et non dans l'URL : l'API journalise les chemins, pas les corps. */
	lireDesabonnement(jeton: string): Promise<DemandeDesabonnement> {
		return this.#json('POST', '/api/v1/desabonnements/lecture', { jeton });
	}

	/** Vide les destinataires du profil que le jeton désigne. 404 s'il est invalide ou déjà
	 * servi : l'API ne distingue pas les deux, et le site n'a pas à le faire. */
	desabonner(jeton: string): Promise<{ username: string }> {
		return this.#json('POST', '/api/v1/desabonnements', { jeton });
	}

	/** Ce que le lien de vote désigne, et le vote déjà donné, sans rien écrire. Le jeton
	 * part dans le corps, comme celui du désabonnement. */
	lireRetourParLien(jeton: string): Promise<LectureRetour> {
		return this.#json('POST', '/api/v1/retours/lecture', { jeton });
	}

	/** Le vote du lien de la lettre : le profil et la journée viennent du jeton seul. */
	voterParLien(jeton: string, avis: Avis, commentaire: string): Promise<LectureRetour> {
		return this.#json('POST', '/api/v1/retours', { jeton, avis, commentaire });
	}

	/** Le vote déjà donné sur la journée ; 404 s'il n'y en a pas. */
	lireRetour(username: string, date: string): Promise<Retour> {
		return this.#json('GET', this.#retour(username, date));
	}

	/** Le vote de la personne connectée, qui remplace le précédent. */
	voter(username: string, date: string, avis: Avis, commentaire: string): Promise<Retour> {
		return this.#json('PUT', this.#retour(username, date), { avis, commentaire });
	}

	/** Les votes les plus récents d'abord, bornés par l'API. */
	listerRetours(): Promise<Retour[]> {
		return this.#json('GET', '/api/v1/retours');
	}

	/** Gardés en mémoire quelques minutes : chaque visite anonyme de l'inscription les
	 * demande, deux fois sur une erreur de formulaire, alors que le catalogue ne bouge
	 * presque jamais. Une erreur n'est pas gardée : l'appel suivant réessaie. */
	async listerGabarits(): Promise<Gabarit[]> {
		const maintenant = this.#maintenant();
		if (this.#gabarits && maintenant < this.#gabarits.expireLe) return this.#gabarits.liste;
		const liste = await this.#json<Gabarit[]>('GET', '/api/v1/gabarits');
		this.#gabarits = { liste, expireLe: maintenant + this.#dureeGabaritsMs };
		return liste;
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

	#retour(username: string, date: string): string {
		return `${this.#profil(username)}/journees/${encodeURIComponent(date)}/retour`;
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
		try {
			return (await reponse.json()) as T;
		} catch (cause) {
			// Un corps qui n'est pas du JSON, ou un délai qui expire en pleine lecture. Rendus en
			// `ErreurApi` comme une API muette, pour que les appelants qui font « au mieux » -
			// l'heure du passage dans la bienvenue, la liste des métiers, les rattrapent aussi
			// au lieu de laisser passer une 500 après coup.
			console.error(`API de résumé : réponse illisible (${methode} ${chemin}) :`, cause);
			throw new ErreurApi(0, 'Le service de résumé a rendu une réponse illisible.');
		}
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
		let champ: string | null = null;
		try {
			const corps = (await reponse.json()) as { erreur?: unknown; champ?: unknown };
			if (typeof corps.erreur === 'string' && corps.erreur) message = corps.erreur;
			if (typeof corps.champ === 'string' && corps.champ) champ = corps.champ;
		} catch {
			// Corps absent ou non JSON : le message générique suffit.
		}
		if (reponse.status === 401) {
			// Un 401 est une erreur de déploiement (jeton faux), pas une faute de la personne.
			console.error('API de résumé : jeton refusé (401). Vérifier RSSRESUME_API_TOKEN.');
			message = 'Le service de résumé refuse la connexion du site.';
		}
		return new ErreurApi(reponse.status, message, champ);
	}

	/**
	 * Lit les coûts d’un profil sur 7 et 30 jours.
	 *
	 * Les clés sont en dur dans le code : pas de changement prévu, et le retour est déjà
	 * documenté dans le contrat.
	 */
	lireCouts(username: string): Promise<CoutsProfil> {
		return this.#json('GET', `${this.#profil(username)}/couts`);
	}
}

export interface CoutsPeriode {
	devise: string;
	total: number | null;
	tarification_complete: boolean;
	modeles_sans_tarif: string[];
}

export interface CoutsProfil {
	couts_7j: CoutsPeriode;
	couts_30j: CoutsPeriode;
}
