import { DatabaseSync } from 'node:sqlite';
import { describe, expect, it } from 'vitest';
import { migrer } from './base.js';
import { ErreurMagicLink } from './magic-link.js';
import { monter, ORIGINE } from './outils-test.js';

const IP = '192.168.1.1';
const EMAIL = 'test@example.com';

/** Le jeton du dernier lien magique envoyé, relu dans le texte du message. */
function jetonEnvoye(courrier: { envoyes: { texte: string }[] }): string {
	const texte = courrier.envoyes.at(-1)?.texte ?? '';
	const trouve = /\/magic-link\/([A-Za-z0-9_-]+)/.exec(texte);
	if (!trouve) throw new Error(`pas de lien magique dans : ${texte}`);
	return trouve[1];
}

describe('MagicLink', () => {
	it('envoie un lien magique pour un nouvel email', async () => {
		const { magicLink, courrier } = monter();
		const resultat = await magicLink.demander(EMAIL, ORIGINE, IP);

		expect(resultat).toEqual({ envoye: true, email: EMAIL });
		expect(courrier.envoyes).toHaveLength(1);
		expect(courrier.envoyes[0].sujet).toBe('RSSResume : votre lien de connexion');
		expect(courrier.envoyes[0].texte).toContain(`${ORIGINE}/magic-link/`);
	});

	it('répond de même pour une adresse connue et une inconnue', async () => {
		const { magicLink, creerConfirme } = monter();
		await creerConfirme(EMAIL, 'testuser');

		const connue = await magicLink.demander(EMAIL, ORIGINE, IP);
		const inconnue = await magicLink.demander('inconnu@example.com', ORIGINE, IP);

		expect(connue.envoye).toBe(true);
		expect(inconnue.envoye).toBe(true);
	});

	it('limite à 5 demandes par heure et par email', async () => {
		const { magicLink } = monter();
		for (let i = 0; i < 5; i++) await magicLink.demander(EMAIL, ORIGINE, `10.0.0.${i}`);

		await expect(magicLink.demander(EMAIL, ORIGINE, '10.0.0.9')).rejects.toEqual(
			new ErreurMagicLink('limite')
		);
	});

	it('limite à 5 demandes par heure et par IP', async () => {
		const { magicLink } = monter();
		for (let i = 0; i < 5; i++) await magicLink.demander(`test${i}@example.com`, ORIGINE, IP);

		await expect(magicLink.demander('test6@example.com', ORIGINE, IP)).rejects.toEqual(
			new ErreurMagicLink('limite')
		);
	});

	it('rouvre les demandes une heure plus tard', async () => {
		const h = { t: 1_000_000_000 };
		const { magicLink } = monter(() => h.t);
		for (let i = 0; i < 5; i++) await magicLink.demander(EMAIL, ORIGINE, IP);

		h.t += 60 * 60 * 1000 + 1;
		await expect(magicLink.demander(EMAIL, ORIGINE, IP)).resolves.toMatchObject({ envoye: true });
	});

	it('crée un compte sans mot de passe, en attente, à la première demande', async () => {
		const { magicLink, comptes } = monter();
		await magicLink.demander(EMAIL, ORIGINE, IP);

		const utilisateur = comptes.parEmail(EMAIL);
		expect(utilisateur?.confirme).toBe(false);
		expect(comptes.aUnMotDePasse(utilisateur!.id)).toBe(false);
	});

	it('ouvre la session du compte et le confirme', async () => {
		const { magicLink, comptes, courrier } = monter();
		await magicLink.demander(EMAIL, ORIGINE, IP);

		const utilisateur = magicLink.valider(jetonEnvoye(courrier));

		expect(utilisateur?.email).toBe(EMAIL);
		expect(comptes.parEmail(EMAIL)?.confirme).toBe(true);
	});

	it('ne sert qu’une fois', async () => {
		const { magicLink, courrier } = monter();
		await magicLink.demander(EMAIL, ORIGINE, IP);
		const jeton = jetonEnvoye(courrier);

		expect(magicLink.valider(jeton)).not.toBeNull();
		expect(magicLink.valider(jeton)).toBeNull();
	});

	it('invalide le lien précédent à chaque nouvelle demande', async () => {
		const { magicLink, courrier } = monter(() => 1_000_000_000);
		await magicLink.demander(EMAIL, ORIGINE, IP);
		const ancien = jetonEnvoye(courrier);
		// Dans la même milliseconde : le double clic ne doit pas faire échouer la seconde demande.
		await magicLink.demander(EMAIL, ORIGINE, IP);

		expect(magicLink.valider(ancien)).toBeNull();
		expect(magicLink.valider(jetonEnvoye(courrier))).not.toBeNull();
	});

	it('refuse un jeton inconnu', () => {
		const { magicLink } = monter();
		expect(magicLink.valider('inexistant')).toBeNull();
	});

	it('garde les demandes déjà comptées en levant la clé primaire', () => {
		const base = new DatabaseSync(':memory:');
		migrer(base, 7);
		base.prepare('INSERT INTO magic_link_demandes VALUES (?, ?, ?)').run(EMAIL, IP, 42);
		migrer(base);

		base.prepare('INSERT INTO magic_link_demandes VALUES (?, ?, ?)').run(EMAIL, IP, 42);
		expect(base.prepare('SELECT COUNT(*) AS n FROM magic_link_demandes').get()).toEqual({ n: 2 });
	});

	it('prend la partie locale de l’adresse comme nom, suffixée si elle est prise', async () => {
		const { magicLink, comptes, creerConfirme } = monter();
		await creerConfirme('test@ailleurs.example', 'test');

		await magicLink.demander(EMAIL, ORIGINE, IP);

		expect(comptes.parEmail(EMAIL)?.username).toBe('test1');
	});
});
