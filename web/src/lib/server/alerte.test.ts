import { describe, expect, it } from 'vitest';
import { AlerteInscription } from './alerte.js';

const INSCRIT = { username: 'moi', email: 'moi@example.com' };

describe('AlerteInscription', () => {
	it("poste l'alerte à Resend avec la clé en Bearer", async () => {
		const envois: Request[] = [];
		const alerte = new AlerteInscription({
			cleApi: 're_cle',
			expediteur: 'RSSResume <site@example.com>',
			destinataire: 'admin@example.test',
			fetch: async (entree, init) => {
				envois.push(new Request(entree, init));
				return new Response('{"id":"1"}', { status: 200 });
			}
		});
		expect(await alerte.envoyer(INSCRIT)).toBe(true);
		const [envoi] = envois;
		expect(envoi.url).toBe('https://api.resend.com/emails');
		expect(envoi.headers.get('authorization')).toBe('Bearer re_cle');
		const corps = await envoi.json();
		expect(corps).toMatchObject({
			from: 'RSSResume <site@example.com>',
			to: ['admin@example.test']
		});
		expect(corps.text).toContain('moi@example.com');
	});

	it("n'appelle rien quand la configuration manque", async () => {
		let appels = 0;
		const alerte = new AlerteInscription({
			cleApi: '',
			expediteur: 'site@example.com',
			destinataire: 'admin@example.test',
			fetch: async () => {
				appels++;
				return new Response();
			}
		});
		expect(alerte.configuree).toBe(false);
		expect(await alerte.envoyer(INSCRIT)).toBe(false);
		expect(appels).toBe(0);
	});

	it('ne lève pas quand Resend refuse ou ne répond pas', async () => {
		const refus = new AlerteInscription({
			cleApi: 'k',
			expediteur: 'a@example.com',
			destinataire: 'b@example.com',
			fetch: async () => new Response('{"message":"domaine non vérifié"}', { status: 403 })
		});
		expect(await refus.envoyer(INSCRIT)).toBe(false);

		const panne = new AlerteInscription({
			cleApi: 'k',
			expediteur: 'a@example.com',
			destinataire: 'b@example.com',
			fetch: () => Promise.reject(new TypeError('fetch failed'))
		});
		expect(await panne.envoyer(INSCRIT)).toBe(false);
	});
});
