import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { marquerLesEcoutes, signalerEcoute } from './ecoute.js';
import type { LecteurAudio, PisteAudio } from './lecteur.svelte.js';

/** Un lecteur réduit à son annonce de fin : le test la déclenche à la main. */
function faux(): { lecteur: Pick<LecteurAudio, 'surEcouteTerminee'>; finir: (piste: PisteAudio) => void } {
	const abonnes = new Set<(piste: PisteAudio) => void>();
	return {
		lecteur: {
			surEcouteTerminee(rappel) {
				abonnes.add(rappel);
				return () => abonnes.delete(rappel);
			}
		},
		finir: (piste) => abonnes.forEach((rappel) => rappel(piste))
	};
}

function piste(journeeEntiere: boolean): PisteAudio {
	return { username: 'bea', date: '2026-11-22', journeeEntiere } as PisteAudio;
}

describe("signalement de l'écoute", () => {
	let fetch: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
		vi.stubGlobal('fetch', fetch);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('marque la journée quand le lecteur annonce la fin d’une piste de journée entière', () => {
		const { lecteur, finir } = faux();
		marquerLesEcoutes(lecteur);

		finir(piste(true));

		expect(fetch).toHaveBeenCalledExactlyOnceWith('/resumes/bea/2026-11-22/ecoute', {
			method: 'POST',
			keepalive: true
		});
	});

	it("ne marque rien pour une catégorie seule, ni après désabonnement", () => {
		const { lecteur, finir } = faux();
		const desabonner = marquerLesEcoutes(lecteur);

		finir(piste(false));
		desabonner();
		finir(piste(true));

		expect(fetch).not.toHaveBeenCalled();
	});

	it('signale directement une journée connue, segments encodés, et dit si le site a marqué', async () => {
		expect(await signalerEcoute('bea', '2026-11-22')).toBe(true);
		await signalerEcoute('a/b', '2026-11-22');

		expect(fetch).toHaveBeenNthCalledWith(1, '/resumes/bea/2026-11-22/ecoute', { method: 'POST', keepalive: true });
		expect(fetch.mock.calls[1][0]).toBe('/resumes/a%2Fb/2026-11-22/ecoute');
	});

	it('rend faux, sans lever, sur un refus du site ou un échec du réseau', async () => {
		fetch.mockImplementation(() => Promise.resolve(new Response(null, { status: 404 })));
		expect(await signalerEcoute('bea', '2026-11-22')).toBe(false);

		fetch.mockImplementation(() => Promise.reject(new TypeError('fetch failed')));
		expect(await signalerEcoute('bea', '2026-11-22')).toBe(false);
	});
});
