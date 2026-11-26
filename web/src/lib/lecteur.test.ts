import { describe, expect, it } from 'vitest';
import { LecteurAudio, PisteAudio, minutesSecondes, type ElementAudio } from './lecteur.svelte.js';

/** Un `<audio>` réduit à ce que le lecteur en voit : Node n'a pas d'`Audio`. Il compte les
 * `play()` et `pause()`, pour qu'un test voie qu'une navigation n'a rien relancé. */
class FauxAudio extends EventTarget implements ElementAudio {
	src = '';
	currentTime = 0;
	duration = Number.NaN;
	paused = true;
	lectures = 0;
	pauses = 0;

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

	it('annonce une écoute terminée une seule fois par piste, et plus après désabonnement', () => {
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

	it('cherche, suit la durée et se ferme', () => {
		const { lecteur, elements } = monter();
		lecteur.lancer(A);
		elements[0].duration = 120;
		elements[0].dispatchEvent(new Event('loadedmetadata'));
		lecteur.chercher(30);
		expect(elements[0].currentTime).toBe(30);
		expect(lecteur.duree).toBe(120);
		expect(lecteur.progression).toBe(0.25);

		lecteur.fermer();
		expect(lecteur.piste).toBeNull();
		expect(lecteur.afficherMini).toBe(false);
		expect(elements[0].paused).toBe(true);
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
