/**
 * Le lecteur audio du site : un seul, porté par le layout, qui survit aux navigations.
 *
 * Un `<audio>` posé dans une page meurt avec elle : SvelteKit démonte la page au changement
 * de route, et le son s'arrête. L'élément vit donc ici, hors de tout markup, créé à la
 * première écoute et réutilisé ensuite — d'où « un seul audio à la fois » sans rien à
 * coordonner. Les pages ne font que le piloter (`LecteurPlein`) ; le layout montre le
 * mini-lecteur (`LecteurGlobal`) quand aucune page n'offre d'emplacement à la piste en cours.
 */
import { getContext, setContext } from 'svelte';

/** Une écoute : la journée entière (montage, carte de la liste) ou une seule catégorie. */
export class PisteAudio {
	constructor(
		readonly username: string,
		readonly date: string,
		readonly nom: string,
		readonly titre: string,
		readonly journeeEntiere: boolean
	) {}

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

	/** L'élément n'est fabriqué qu'à la première écoute : sous SSR, `Audio` n'existe pas, et
	 * le lecteur est construit à chaque requête. */
	constructor(private readonly creerElement: () => ElementAudio = () => new Audio()) {}

	/** Le mini-lecteur ne double pas un lecteur plein déjà à l'écran pour la même piste. */
	get afficherMini(): boolean {
		return this.piste !== null && !this.#ancres[this.piste.cle];
	}

	get progression(): number {
		return this.duree > 0 ? Math.min(1, this.position / this.duree) : 0;
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
		this.#jouer(element);
	}

	basculer(): void {
		if (!this.piste || !this.#element) return;
		if (this.#element.paused) this.#jouer(this.#element);
		else this.#element.pause();
	}

	pause(): void {
		this.#element?.pause();
	}

	chercher(secondes: number): void {
		if (!this.#element || !Number.isFinite(secondes)) return;
		this.#element.currentTime = secondes;
		this.position = secondes;
	}

	/** Arrête et oublie la piste : le mini-lecteur disparaît, l'élément reste pour la suivante. */
	fermer(): void {
		this.#element?.pause();
		this.piste = null;
		this.position = 0;
		this.duree = 0;
	}

	/** Déclare qu'une page montre cette piste en lecteur plein ; la fonction rendue la retire,
	 * ce que fait le démontage du composant quand on quitte la page. */
	ancrer(cle: string): () => void {
		this.#ancres[cle] = (this.#ancres[cle] ?? 0) + 1;
		let retiree = false;
		return () => {
			if (retiree) return;
			retiree = true;
			const reste = (this.#ancres[cle] ?? 1) - 1;
			if (reste > 0) this.#ancres[cle] = reste;
			else delete this.#ancres[cle];
		};
	}

	/** Prévient d'une écoute menée à son terme, une fois par piste lancée. Le lecteur ne fait
	 * qu'annoncer : ce que cela vaut (marquer la journée lue…) est l'affaire de l'abonné. */
	surEcouteTerminee(rappel: (piste: PisteAudio) => void): () => void {
		this.#abonnes.add(rappel);
		return () => {
			this.#abonnes.delete(rappel);
		};
	}

	#jouer(element: ElementAudio): void {
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
