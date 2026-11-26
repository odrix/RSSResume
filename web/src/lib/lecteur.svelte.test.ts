import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import { LecteurAudio, PisteAudio, minutesSecondes, type ElementAudio } from './lecteur.svelte.js';

/* Fichier `.svelte.test.ts`, compilé pour le client (projet `runes` de `vite.config.ts`) : les
 * runes y sont actives, ce qui permet de faire tourner `ancrer` dans un vrai `$effect`, là où
 * le rendu serveur des composants n'en lance aucun. */

/** Un `<audio>` réduit à ce que le lecteur en voit : Node n'a pas d'`Audio`. Il compte les
 * `play()` et `pause()`, pour qu'un test voie qu'une navigation n'a rien relancé. */
class FauxAudio extends EventTarget implements ElementAudio {
	src = '';
	currentTime = 0;
	duration = Number.NaN;
	paused = true;
	lectures = 0;
	pauses = 0;
	chargements = 0;

	play(): Promise<void> {
		this.lectures += 1;
		this.paused = false;
		this.dispatchEvent(new Event('play'));
		return Promise.resolve();
	}

	pause(): void {
		this.pauses += 1;
		if (this.paused) return;
		this.paused = true;
		this.dispatchEvent(new Event('pause'));
	}

	load(): void {
		this.chargements += 1;
	}

	removeAttribute(nom: string): void {
		if (nom === 'src') this.src = '';
	}

	avancer(secondes: number): void {
		this.currentTime = secondes;
		this.dispatchEvent(new Event('timeupdate'));
	}

	terminer(): void {
		this.paused = true;
		this.dispatchEvent(new Event('ended'));
	}
}

function monter() {
	const elements: FauxAudio[] = [];
	const lecteur = new LecteurAudio(() => {
		const element = new FauxAudio();
		elements.push(element);
		return element;
	});
	return { lecteur, elements };
}

const A = new PisteAudio('moi', '2026-11-21', 'journee.mp3', 'Vendredi 21 novembre 2026', true);
const B = new PisteAudio('moi', '2026-11-22', 'journee.mp3', 'Samedi 22 novembre 2026', true);

describe('PisteAudio', () => {
	it('passe par le relais du site et pointe vers la page de sa journée', () => {
		const piste = new PisteAudio('é t', '2026-11-21', 'a b.mp3', 'x', false);
		expect(piste.url).toBe('/audio/%C3%A9%20t/2026-11-21/a%20b.mp3');
		expect(piste.pageJournee).toBe('/resumes/%C3%A9%20t/2026-11-21');
		expect(piste.cle).toBe('é t/2026-11-21/a b.mp3');
	});

	it("ne se présente comme la journée entière que pour son montage", () => {
		const montage = PisteAudio.pourFichier('moi', '2026-11-21', 'journee.mp3', 'journee.mp3', null);
		expect(montage.journeeEntiere).toBe(true);
		expect(montage.titre).toBe('Samedi 21 novembre 2026');

		// Mode par catégorie : le premier fichier n'est qu'une catégorie.
		const categorie = PisteAudio.pourFichier('moi', '2026-11-21', 'cyber.mp3', null, 'Cyber');
		expect(categorie.journeeEntiere).toBe(false);
		expect(categorie.titre).toBe('Samedi 21 novembre 2026 · Cyber');

		const inconnue = PisteAudio.pourFichier('moi', '2026-11-21', 'cyber.mp3', 'journee.mp3', null);
		expect(inconnue.journeeEntiere).toBe(false);
		expect(inconnue.titre).toBe('Samedi 21 novembre 2026 · cyber.mp3');
	});
});

describe('LecteurAudio', () => {
	it("ne fabrique aucun élément tant qu'on n'a rien lancé (rendu serveur)", () => {
		const { lecteur, elements } = monter();
		expect(elements).toHaveLength(0);
		expect(lecteur.afficherMini).toBe(false);
	});

	it('survit à une navigation : ancrer puis désancrer ne touche ni la source, ni la position, ni la lecture', () => {
		const { lecteur, elements } = monter();
		lecteur.lancer(A);
		const [element] = elements;
		element.avancer(42);
		const avant = { src: element.src, lectures: element.lectures, pauses: element.pauses };

		// La page de la journée s'ouvre (lecteur plein), puis on la quitte.
		const desancrer = lecteur.ancrer(A.cle);
		expect(lecteur.afficherMini).toBe(false);
		desancrer();
		expect(lecteur.afficherMini).toBe(true);

		expect(element.src).toBe(avant.src);
		expect(element.currentTime).toBe(42);
		expect(lecteur.position).toBe(42);
		expect(element.lectures).toBe(avant.lectures);
		expect(element.pauses).toBe(avant.pauses);
		expect(lecteur.enLecture).toBe(true);

		// Relancer la même journée depuis une autre page reprend où l'on en était.
		lecteur.lancer(new PisteAudio('moi', '2026-11-21', 'journee.mp3', 'autre titre', true));
		expect(element.currentTime).toBe(42);
		expect(lecteur.position).toBe(42);
		expect(element.lectures).toBe(avant.lectures);
	});

	it("s'ancre depuis un $effect sans boucler, et afficherMini suit l'ancrage", () => {
		const { lecteur } = monter();
		lecteur.lancer(A);
		let executions = 0;
		const vus: boolean[] = [];

		// Le mini-lecteur du layout : il lit `afficherMini` et doit voir chaque changement.
		const arreterObservation = $effect.root(() => {
			$effect(() => {
				vus.push(lecteur.afficherMini);
			});
		});
		flushSync();
		expect(vus).toEqual([true]);

		// Ce que fait `LecteurPlein` dans le navigateur : l'effet ancre, son nettoyage désancre.
		const demonterPage = $effect.root(() => {
			$effect(() => {
				executions += 1;
				return lecteur.ancrer(A.cle);
			});
		});
		flushSync();

		// Sans `untrack`, l'effet relirait ce qu'il vient d'écrire et Svelte lèverait
		// `effect_update_depth_exceeded` ; ici il n'est passé qu'une fois.
		expect(executions).toBe(1);
		expect(vus).toEqual([true, false]);

		// Un second emplacement de la même piste ne relance pas le premier.
		lecteur.ancrer(A.cle)();
		flushSync();
		expect(executions).toBe(1);

		// On quitte la page : le mini-lecteur réapparaît.
		demonterPage();
		flushSync();
		expect(executions).toBe(1);
		expect(vus.at(-1)).toBe(true);
		arreterObservation();
	});

	it('reprend une piste en pause sans revenir au début', () => {
		const { lecteur, elements } = monter();
		lecteur.lancer(A);
		elements[0].avancer(10);
		lecteur.basculer();
		expect(lecteur.enLecture).toBe(false);
		lecteur.lancer(A);
		expect(lecteur.enLecture).toBe(true);
		expect(elements[0].currentTime).toBe(10);
	});

	it("n'a qu'un audio : lancer une autre journée remplace la première", () => {
		const { lecteur, elements } = monter();
		const terminees: PisteAudio[] = [];
		lecteur.surEcouteTerminee((piste) => terminees.push(piste));

		lecteur.lancer(A);
		elements[0].avancer(42);
		lecteur.lancer(B);

		expect(elements).toHaveLength(1);
		expect(elements[0].src).toBe(B.url);
		expect(elements[0].currentTime).toBe(0);
		expect(lecteur.position).toBe(0);
		expect(lecteur.piste).toBe(B);
		expect(lecteur.enLecture).toBe(true);

		elements[0].terminer();
		expect(terminees).toEqual([B]);
	});

	it('annonce une écoute terminée une seule fois par écoute, et plus après désabonnement', () => {
		const { lecteur, elements } = monter();
		const terminees: PisteAudio[] = [];
		const desabonner = lecteur.surEcouteTerminee((piste) => terminees.push(piste));

		lecteur.lancer(A);
		elements[0].terminer();
		elements[0].terminer();
		expect(terminees).toEqual([A]);
		expect(lecteur.enLecture).toBe(false);

		desabonner();
		lecteur.lancer(B);
		elements[0].terminer();
		expect(terminees).toEqual([A]);
	});

	it('réécoute une piste terminée depuis le début, et en annonce de nouveau la fin', () => {
		const { lecteur, elements } = monter();
		const terminees: PisteAudio[] = [];
		lecteur.surEcouteTerminee((piste) => terminees.push(piste));

		lecteur.lancer(A);
		elements[0].avancer(120);
		elements[0].terminer();
		expect(terminees).toEqual([A]);

		lecteur.lancer(A);
		expect(elements[0].currentTime).toBe(0);
		expect(lecteur.position).toBe(0);
		expect(lecteur.enLecture).toBe(true);
		elements[0].terminer();
		expect(terminees).toEqual([A, A]);

		// Même chose par le bouton lecture/pause du mini-lecteur.
		lecteur.basculer();
		elements[0].terminer();
		expect(terminees).toEqual([A, A, A]);
	});

	it('cherche et suit la durée', () => {
		const { lecteur, elements } = monter();
		lecteur.lancer(A);
		elements[0].duration = 120;
		elements[0].dispatchEvent(new Event('loadedmetadata'));
		lecteur.chercher(30);
		expect(elements[0].currentTime).toBe(30);
		expect(lecteur.position).toBe(30);
		expect(lecteur.duree).toBe(120);
	});

	it('se ferme en retirant la source et en remettant tout à zéro', () => {
		const { lecteur, elements } = monter();
		lecteur.lancer(A);
		elements[0].duration = 120;
		elements[0].dispatchEvent(new Event('loadedmetadata'));
		elements[0].avancer(30);

		lecteur.fermer();

		expect(elements[0].paused).toBe(true);
		expect(elements[0].src).toBe('');
		expect(elements[0].chargements).toBe(1);
		expect(lecteur.piste).toBeNull();
		expect(lecteur.enLecture).toBe(false);
		expect(lecteur.position).toBe(0);
		expect(lecteur.duree).toBe(0);
		expect(lecteur.afficherMini).toBe(false);

		// La même piste se relance ensuite comme une nouvelle.
		lecteur.lancer(A);
		expect(elements[0].src).toBe(A.url);
		expect(elements).toHaveLength(1);
	});

	it('garde une piste ancrée tant que tous ses emplacements ne sont pas retirés', () => {
		const { lecteur } = monter();
		lecteur.lancer(A);
		const premier = lecteur.ancrer(A.cle);
		const second = lecteur.ancrer(A.cle);
		premier();
		premier();
		expect(lecteur.afficherMini).toBe(false);
		second();
		expect(lecteur.afficherMini).toBe(true);
	});
});

describe('minutesSecondes', () => {
	it('écrit le temps comme un lecteur natif, zéro tant que la durée est inconnue', () => {
		expect(minutesSecondes(30)).toBe('0:30');
		expect(minutesSecondes(125.7)).toBe('2:05');
		expect(minutesSecondes(Number.NaN)).toBe('0:00');
	});
});
