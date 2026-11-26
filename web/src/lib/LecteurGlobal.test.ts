import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import LecteurGlobal from './LecteurGlobal.svelte';
import { CLE_LECTEUR, LecteurAudio, PisteAudio, type ElementAudio } from './lecteur.svelte.js';

/** Juste assez d'`<audio>` pour placer le lecteur à un instant donné de l'écoute. */
class FauxAudio extends EventTarget implements ElementAudio {
	src = '';
	currentTime = 0;
	duration = Number.NaN;
	paused = true;

	play(): Promise<void> {
		this.paused = false;
		this.dispatchEvent(new Event('play'));
		return Promise.resolve();
	}

	pause(): void {
		this.paused = true;
		this.dispatchEvent(new Event('pause'));
	}

	load(): void {}

	removeAttribute(): void {}
}

const PISTE = new PisteAudio('moi', '2026-11-21', 'journee.mp3', 'Vendredi 21 novembre 2026', true);

function lecteurA(position: number, duree: number): LecteurAudio {
	const element = new FauxAudio();
	const lecteur = new LecteurAudio(() => element);
	lecteur.lancer(PISTE);
	element.duration = duree;
	element.dispatchEvent(new Event('loadedmetadata'));
	element.currentTime = position;
	element.dispatchEvent(new Event('timeupdate'));
	return lecteur;
}

const rendre = (lecteur: LecteurAudio) =>
	render(LecteurGlobal, { context: new Map([[CLE_LECTEUR, lecteur]]) }).body.replace(/<!--[\s\S]*?-->/g, '');

describe('LecteurGlobal', () => {
	it('montre la journée en cours, sa progression et les commandes de base', () => {
		const html = rendre(lecteurA(30, 120));
		expect(html).toContain('mini-lecteur');
		expect(html).toContain('Vendredi 21 novembre 2026');
		expect(html).toContain('<progress value="30" max="120"');
		expect(html).toContain('0:30 / 2:00');
		expect(html).toContain('aria-label="Pause"');
		expect(html).toContain('aria-label="Fermer le lecteur"');
		expect(html).toContain('href="/resumes/moi/2026-11-21"');
	});

	it("s'efface quand la page montre déjà la piste en lecteur plein", () => {
		const lecteur = lecteurA(30, 120);
		lecteur.ancrer(PISTE.cle);
		expect(rendre(lecteur)).not.toContain('mini-lecteur');
	});

	it("ne rend rien tant qu'aucune journée n'est lancée : pas de lecteur vide", () => {
		const html = rendre(new LecteurAudio(() => new FauxAudio()));
		expect(html).not.toContain('mini-lecteur');
		expect(html).not.toContain('<audio');
		expect(html.trim()).toBe('');
	});
});
