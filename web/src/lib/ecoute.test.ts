import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { signalerEcoute, signalerEcouteTerminee } from './ecoute.js';

/** Un `ended` tel que le lecteur l'émet : seule sa source compte. */
function finDeLecture(currentSrc: string): Event {
	return { currentTarget: { currentSrc } } as unknown as Event;
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

	it('relit la journée dans la source du relais, la signale par un POST et rend sa date', async () => {
		const date = await signalerEcouteTerminee(finDeLecture('/audio/bea/2026-11-22/jour.mp3'));

		expect(fetch).toHaveBeenCalledExactlyOnceWith('/resumes/bea/2026-11-22/ecoute', {
			method: 'POST',
			keepalive: true
		});
		expect(date).toBe('2026-11-22');
	});

	it("ne signale rien pour une source qui n'est pas le relais du site", async () => {
		expect(await signalerEcouteTerminee(finDeLecture('/autre/bea/2026-11-22/jour.mp3'))).toBeNull();
		expect(
			await signalerEcouteTerminee(finDeLecture('https://ailleurs.test/audio/bea/2026-11-22/jour.mp3'))
		).toBeNull();
		expect(await signalerEcouteTerminee(finDeLecture(''))).toBeNull();

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
		expect(await signalerEcouteTerminee(finDeLecture('/audio/bea/2026-11-22/jour.mp3'))).toBeNull();

		fetch.mockImplementation(() => Promise.reject(new TypeError('fetch failed')));
		expect(await signalerEcoute('bea', '2026-11-22')).toBe(false);
	});
});
