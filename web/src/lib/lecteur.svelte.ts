/**
 * Le lecteur audio du site : un seul, porté par le layout, qui survit aux navigations.
 *
 * Un `<audio>` posé dans une page meurt avec elle : SvelteKit démonte la page au changement
 * de route, et le son s'arrête. L'élément vit donc ici, hors de tout markup, créé à la
 * première écoute et réutilisé ensuite — d'où « un seul audio à la fois » sans rien à
 * coordonner. Les pages ne font que le piloter (`LecteurPlein`) ; le layout montre le
 * mini-lecteur (`LecteurGlobal`) quand aucune page n'offre d'emplacement à la piste en cours.
 */
import { getContext, setContext, untrack } from 'svelte';
import { dateLisible } from '#lib/journee.js';

/** Une écoute : la journée entière (son montage) ou une seule catégorie. */
export class PisteAudio {
	constructor(
		readonly username: string,
		readonly date: string,
		readonly nom: string,
		readonly titre: string,
		readonly journeeEntiere: boolean
	) {}

	/** La piste d'un fichier de la journée, présentée comme la journée entière seulement si
	 * c'est son montage — la règle de la page de la journée (`contenu.montage.audio`). En mode
	 * par catégorie, le premier fichier n'est qu'une catégorie : le titre le dit, sans quoi le
	 * mini-lecteur annoncerait la journée en ne jouant qu'un morceau. */
	static pourFichier(
		username: string,
		date: string,
		nom: string,
		montage: string | null,
		categorie: string | null
	): PisteAudio {
		if (montage !== null && nom === montage) {
			return new PisteAudio(username, date, nom, dateLisible(date), true);
		}
		return new PisteAudio(username, date, nom, `${dateLisible(date)} · ${categorie ?? nom}`, false);
	}

	/** Le relais du site, jamais l'API : il contrôle le droit d'écouter et sert le `Range`. */
	get url(): string {
		return `/audio/${encodeURIComponent(this.username)}/${encodeURIComponent(this.date)}/${encodeURIComponent(this.nom)}`;
	}

	/** Ce qui fait qu'une piste est « la même » d'une page à l'autre, quand l'objet ne l'est pas. */
	get cle(): string {
		return `${this.username}/${this.date}/${this.nom}`;
	}

	get pageJournee(): string {
		return `/resumes/${encodeURIComponent(this.username)}/${encodeURIComponent(this.date)}`;
	}
}

/** Ce que le lecteur utilise d'un `HTMLMediaElement` : assez étroit pour qu'un faux le remplace
 * dans les tests, qui tournent sous Node, sans `Audio`. */
export interface ElementAudio {
	src: string;
	currentTime: number;
	readonly duration: number;
	readonly paused: boolean;
	play(): Promise<void> | void;
	pause(): void;
	load(): void;
	removeAttribute(nom: string): void;
	addEventListener(type: string, ecouteur: () => void): void;
}

/** `m:ss`, comme les lecteurs natifs ; vide de sens tant que la durée n'est pas connue. */
export function minutesSecondes(secondes: number): string {
	const total = Number.isFinite(secondes) && secondes > 0 ? Math.floor(secondes) : 0;
	return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export class LecteurAudio {
	piste = $state<PisteAudio | null>(null);
	enLecture = $state(false);
	position = $state(0);
	duree = $state(0);

	/** Les clés qu'une page affiche en lecteur plein, comptées : deux emplacements de la même
	 * piste ne se désancrent pas l'un l'autre. */
	#ancres = $state<Record<string, number>>({});
	#element: ElementAudio | null = null;
	#abonnes = new Set<(piste: PisteAudio) => void>();
	#termineeNotifiee = false;
	/** Vrai entre `ended` et la relecture : rejouer repart alors de zéro, et compte comme une
	 * nouvelle écoute, à annoncer de nouveau quand elle s'achève. */
	#finie = false;

	/** L'élément n'est fabriqué qu'à la première écoute : sous SSR, `Audio` n'existe pas, et
	 * le lecteur est construit à chaque requête. */
	constructor(private readonly creerElement: () => ElementAudio = () => new Audio()) {}

	/** Le mini-lecteur ne double pas un lecteur plein déjà à l'écran pour la même piste. */
	get afficherMini(): boolean {
		return this.piste !== null && !this.#ancres[this.piste.cle];
	}

	lancer(piste: PisteAudio): void {
		const element = this.#elementAudio();
		if (this.piste?.cle === piste.cle) {
			// Même piste depuis une autre page : on reprend où l'on en est, jamais au début.
			this.piste = piste;
			if (element.paused) this.#jouer(element);
			return;
		}
		element.pause();
		element.src = piste.url;
		element.currentTime = 0;
		this.piste = piste;
		this.position = 0;
		this.duree = 0;
		this.#termineeNotifiee = false;
		this.#finie = false;
		this.#jouer(element);
	}

	basculer(): void {
		if (!this.piste || !this.#element) return;
		if (this.#element.paused) this.#jouer(this.#element);
		else this.#element.pause();
	}

	chercher(secondes: number): void {
		if (!this.#element || !Number.isFinite(secondes)) return;
		this.#element.currentTime = secondes;
		this.position = secondes;
	}

	/** Arrête et oublie la piste. La source est retirée, et non seulement mise en pause : le
	 * navigateur cesserait sinon de télécharger le MP3 qu'on ne veut plus. */
	fermer(): void {
		const element = this.#element;
		if (element) {
			element.pause();
			element.removeAttribute('src');
			element.load();
		}
		this.piste = null;
		this.enLecture = false;
		this.position = 0;
		this.duree = 0;
		this.#termineeNotifiee = false;
		this.#finie = false;
	}

	/** Déclare qu'une page montre cette piste en lecteur plein ; la fonction rendue la retire,
	 * ce que fait le démontage du composant quand on quitte la page.
	 *
	 * Appelé depuis un `$effect` : lire le compteur pour l'incrémenter abonnerait l'effet à ce
	 * qu'il écrit, et il se relancerait sans fin. D'où `untrack`, à l'aller comme au retour ;
	 * `afficherMini`, lu ailleurs, reste abonné aux ancres. */
	ancrer(cle: string): () => void {
		untrack(() => (this.#ancres[cle] = (this.#ancres[cle] ?? 0) + 1));
		let retiree = false;
		return () => {
			if (retiree) return;
			retiree = true;
			untrack(() => {
				const reste = (this.#ancres[cle] ?? 1) - 1;
				if (reste > 0) this.#ancres[cle] = reste;
				else delete this.#ancres[cle];
			});
		};
	}

	/** Prévient d'une écoute menée à son terme, une fois par écoute. Le lecteur ne fait
	 * qu'annoncer : ce que cela vaut (marquer la journée lue…) est l'affaire de l'abonné. */
	surEcouteTerminee(rappel: (piste: PisteAudio) => void): () => void {
		this.#abonnes.add(rappel);
		return () => {
			this.#abonnes.delete(rappel);
		};
	}

	#jouer(element: ElementAudio): void {
		if (this.#finie) {
			this.#finie = false;
			this.#termineeNotifiee = false;
			element.currentTime = 0;
			this.position = 0;
		}
		// Le navigateur peut refuser la lecture (politique d'autoplay, fichier introuvable) :
		// la promesse rejetée ne doit pas remonter en erreur non gérée.
		const promesse = element.play();
		if (promesse) promesse.catch(() => (this.enLecture = false));
	}

	#elementAudio(): ElementAudio {
		if (this.#element) return this.#element;
		const element = this.creerElement();
		element.addEventListener('timeupdate', () => (this.position = element.currentTime));
		element.addEventListener('loadedmetadata', () => {
			if (Number.isFinite(element.duration)) this.duree = element.duration;
		});
		element.addEventListener('play', () => (this.enLecture = true));
		element.addEventListener('pause', () => (this.enLecture = false));
		element.addEventListener('ended', () => {
			this.enLecture = false;
			this.#finie = true;
			if (this.#termineeNotifiee || !this.piste) return;
			this.#termineeNotifiee = true;
			const piste = this.piste;
			for (const rappel of this.#abonnes) rappel(piste);
		});
		this.#element = element;
		return element;
	}
}

/** La clé de contexte ; exportée pour que les tests montent un composant avec leur lecteur. */
export const CLE_LECTEUR = Symbol('lecteur-audio');

/** Un lecteur par arbre de composants, pas par module : un `$state` de module serait partagé
 * par toutes les requêtes du serveur, donc entre utilisateurs. */
export function fournirLecteur(lecteur: LecteurAudio): LecteurAudio {
	setContext(CLE_LECTEUR, lecteur);
	return lecteur;
}

export function lecteurAudio(): LecteurAudio {
	const lecteur = getContext<LecteurAudio | undefined>(CLE_LECTEUR);
	if (!lecteur) throw new Error('Aucun lecteur audio fourni : le layout doit appeler fournirLecteur().');
	return lecteur;
}
