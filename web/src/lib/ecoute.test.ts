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

	it("relit la journée dans la source du relais et la signale par un POST", () => {
		signalerEcouteTerminee(finDeLecture('/audio/bea/2026-11-22/jour.mp3'));

		expect(fetch).toHaveBeenCalledExactlyOnceWith('/resumes/bea/2026-11-22/ecoute', {
			method: 'POST',
			keepalive: true
		});
	});

	it("ne signale rien pour une source qui n'est pas le relais du site", () => {
		signalerEcouteTerminee(finDeLecture('/autre/bea/2026-11-22/jour.mp3'));
		signalerEcouteTerminee(finDeLecture('https://ailleurs.test/audio/bea/2026-11-22/jour.mp3'));
		signalerEcouteTerminee(finDeLecture(''));

		expect(fetch).not.toHaveBeenCalled();
	});

	it('signale directement une journée connue, segments encodés', () => {
		signalerEcoute('bea', '2026-11-22');
		signalerEcoute('a/b', '2026-11-22');

		expect(fetch).toHaveBeenNthCalledWith(1, '/resumes/bea/2026-11-22/ecoute', { method: 'POST', keepalive: true });
		expect(fetch.mock.calls[1][0]).toBe('/resumes/a%2Fb/2026-11-22/ecoute');
	});

	it("tait l'échec du réseau", async () => {
		fetch.mockImplementation(() => Promise.reject(new TypeError('fetch failed')));

		expect(() => signalerEcoute('bea', '2026-11-22')).not.toThrow();
		await Promise.resolve();
	});
});
