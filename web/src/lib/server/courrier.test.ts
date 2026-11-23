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

describe('bienvenue', () => {
	it('la bienvenue dit quoi, quand, où ajuster et comment arrêter', async () => {
		const courrier = new CourrierJournal('admin@example.test', false);
		expect(
			await courrier.souhaiterBienvenue(INSCRIT, {
				prenom: 'Adrien',
				libelleMetier: 'CTO, direction technique',
				categories: ['Tech generaliste', 'Cybersécurité'],
				passage: { heure: '04:00', fuseau: 'Europe/Paris', prochain: '2026-11-23T04:00:00+01:00' },
				origine: 'https://site.test'
			})
		).toBe(true);
		const [message] = courrier.envoyes;
		expect(message.destinataire).toBe('moi@example.com');
		expect(message.sujet).toBe('Bienvenue sur RSSResume');
		for (const attendu of [
			'Bonjour Adrien,',
			'Votre compte « moi » est actif.',
			// Quoi.
			'Chaque matin, un email avec les articles de la veille retenus pour vous',
			'épisode audio',
			'gabarit « CTO, direction technique »',
			'Catégories suivies : Tech generaliste, Cybersécurité.',
			// Quand.
			'Le passage quotidien a lieu à 04:00 (Europe/Paris)',
			'suivra celui du lundi 23 novembre',
			// Où ajuster.
			'https://site.test/profil',
			'Vous y choisissez aussi vos catégories et vos rubriques.',
			'https://site.test/resumes',
			'régime de sécurité',
			// Comment arrêter.
			'videz « Adresses de réception » dans Mon profil'
		]) {
			expect(message.texte).toContain(attendu);
		}
	});

	it('sans heure ni gabarit, la bienvenue reste juste', async () => {
		const courrier = new CourrierJournal('admin@example.test', false);
		await courrier.souhaiterBienvenue(INSCRIT, {
			prenom: '',
			libelleMetier: null,
			categories: null,
			passage: null,
			origine: 'https://site.test'
		});
		const [message] = courrier.envoyes;
		expect(message.texte.startsWith('Bonjour,\n')).toBe(true);
		expect(message.texte).toContain('toutes les catégories ouvertes');
		expect(message.texte).toContain('chaque matin, après le passage quotidien');
		expect(message.texte).not.toContain('gabarit');
		expect(message.texte).not.toMatch(/\d\d:\d\d/);
	});
});
