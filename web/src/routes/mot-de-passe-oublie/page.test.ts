import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LimiteurTentatives } from '#lib/server/limiteur.js';
import { monter } from '#lib/server/outils-test.js';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { actions } = await import('./+page.server.js');

function evenement(email: string, ip = '203.0.113.7') {
	const url = new URL('https://site.test/mot-de-passe-oublie');
	return {
		url,
		getClientAddress: () => ip,
		request: new Request(url, {
			method: 'POST',
			headers: { 'content-type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({ email }).toString()
		})
	} as never;
}

describe('/mot-de-passe-oublie', () => {
	let env: ReturnType<typeof monter>;
	beforeEach(async () => {
		env = monter();
		await env.creerConfirme('moi@example.com', 'moi');
		etat.env = {
			...env,
			limiteOublisParEmail: new LimiteurTentatives(3, 60 * 60 * 1000),
			limiteOublisParIp: new LimiteurTentatives(10, 60 * 60 * 1000)
		};
	});

	it("répond la même chose que l'adresse ait un compte ou non", async () => {
		const connue = (await actions.default(evenement('moi@example.com'))) as { envoye: string };
		const inconnue = (await actions.default(evenement('personne@example.com'))) as { envoye: string };

		expect(inconnue.envoye).toBe(connue.envoye);
		expect(Object.keys(inconnue)).toEqual(Object.keys(connue));
		// Seule l'adresse connue a reçu un lien.
		expect(env.courrier.envoyes.map((m) => m.destinataire)).toEqual(['moi@example.com']);
	});

	it('limite les demandes par adresse', async () => {
		for (let i = 0; i < 3; i++) await actions.default(evenement('moi@example.com'));
		const refus = (await actions.default(evenement('moi@example.com'))) as { status: number };
		expect(refus.status).toBe(429);
		expect(env.courrier.envoyes).toHaveLength(3);
	});
});
