import { describe, expect, it } from 'vitest';
import { CourrierAbsent, CourrierJournal, CourrierResend } from './courrier.js';

const INSCRIT = { username: 'moi', email: 'moi@example.com' };

function resendEspion(reponse: () => Promise<Response>) {
	const envois: Request[] = [];
	const courrier = new CourrierResend({
		cleApi: 're_cle',
		expediteur: 'RSSResume <site@example.com>',
		emailAdmin: 'admin@example.test',
		fetch: async (entree, init) => {
			envois.push(new Request(entree, init));
			return reponse();
		}
	});
	return { courrier, envois };
}

describe('CourrierResend', () => {
	it('poste à Resend avec la clé en Bearer', async () => {
		const { courrier, envois } = resendEspion(async () => new Response('{"id":"1"}'));
		expect(await courrier.confirmerInscription(INSCRIT, 'https://site.test/confirmer/abc')).toBe(true);
		const [envoi] = envois;
		expect(envoi.url).toBe('https://api.resend.com/emails');
		expect(envoi.headers.get('authorization')).toBe('Bearer re_cle');
		const corps = await envoi.json();
		expect(corps).toMatchObject({ from: 'RSSResume <site@example.com>', to: ['moi@example.com'] });
		expect(corps.text).toContain('https://site.test/confirmer/abc');
	});

	it("alerte l'administrateur", async () => {
		const { courrier, envois } = resendEspion(async () => new Response('{}'));
		expect(await courrier.alerterAdmin(INSCRIT)).toBe(true);
		const corps = await envois[0].json();
		expect(corps.to).toEqual(['admin@example.test']);
		expect(corps.text).toContain('moi@example.com');
	});

	it('ne lève pas quand Resend refuse ou ne répond pas', async () => {
		const refus = resendEspion(async () => new Response('{"message":"domaine non vérifié"}', { status: 403 }));
		expect(await refus.courrier.alerterAdmin(INSCRIT)).toBe(false);
		const panne = resendEspion(() => Promise.reject(new TypeError('fetch failed')));
		expect(await panne.courrier.alerterAdmin(INSCRIT)).toBe(false);
	});
});

describe('transports de repli', () => {
	it('en développement, garde le message et son lien au lieu de l’envoyer', async () => {
		const courrier = new CourrierJournal('admin@example.test', false);
		expect(courrier.disponible).toBe(true);
		await courrier.confirmerDestinataire('moi', 'autre@example.com', 'https://site.test/confirmer/xyz');
		expect(courrier.envoyes[0]).toMatchObject({ destinataire: 'autre@example.com' });
		expect(courrier.envoyes[0].texte).toContain('https://site.test/confirmer/xyz');
	});

	it('en production sans clé, se dit indisponible et ne prétend rien envoyer', async () => {
		const courrier = new CourrierAbsent('admin@example.test');
		expect(courrier.disponible).toBe(false);
		expect(await courrier.confirmerInscription(INSCRIT, 'x')).toBe(false);
	});

	it("n'alerte personne quand ADMIN_EMAIL est vide", async () => {
		const courrier = new CourrierJournal('', false);
		expect(await courrier.alerterAdmin(INSCRIT)).toBe(false);
		expect(courrier.envoyes).toHaveLength(0);
	});
});
