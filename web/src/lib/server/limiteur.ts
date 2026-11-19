/**
 * Une limitation de tentatives en mémoire, par clé et sur une fenêtre glissante.
 *
 * En mémoire parce que le site tourne en un seul processus : un redémarrage remet les
 * compteurs à zéro, ce qui ne rend à un attaquant que quelques essais de plus contre des
 * mots de passe de douze caractères hachés en Argon2id.
 */

export class LimiteurTentatives {
	readonly #echecs = new Map<string, number[]>();

	constructor(
		private readonly maximum: number,
		private readonly fenetreMs: number,
		private readonly maintenant: () => number = Date.now
	) {}

	/** Vrai tant que la clé a encore droit à un essai. */
	autorise(cle: string): boolean {
		return this.#recents(cle).length < this.maximum;
	}

	/** Le délai avant le prochain essai permis, en secondes, pour le message affiché. */
	attenteSecondes(cle: string): number {
		const recents = this.#recents(cle);
		if (recents.length < this.maximum) return 0;
		return Math.ceil((recents[0] + this.fenetreMs - this.maintenant()) / 1000);
	}

	noter(cle: string): void {
		const recents = this.#recents(cle);
		recents.push(this.maintenant());
		this.#echecs.set(cle, recents);
		// Borne la mémoire : un balayage de temps en temps suffit à ce volume.
		if (this.#echecs.size > 10_000) this.#purger();
	}

	oublier(cle: string): void {
		this.#echecs.delete(cle);
	}

	#recents(cle: string): number[] {
		const limite = this.maintenant() - this.fenetreMs;
		const recents = (this.#echecs.get(cle) ?? []).filter((instant) => instant > limite);
		if (recents.length) this.#echecs.set(cle, recents);
		else this.#echecs.delete(cle);
		return recents;
	}

	#purger(): void {
		for (const cle of [...this.#echecs.keys()]) this.#recents(cle);
	}
}
