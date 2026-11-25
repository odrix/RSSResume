import { describe, expect, it, beforeEach, vi } from 'vitest';
import { MagicLink, ErreurMagicLink, type ResultatDemande } from './magic-link.js';
import { Comptes, HacheurMotDePasse } from './comptes.js';
import { JetonsEmail, DUREE_MAGIC_LINK_MS, type JetonLu } from './jetons-email.js';
import { ouvrirBaseTest } from './outils-test.js';
import { CourrierJournal } from './courrier.js';
import { normaliserEmail } from './validation.js';

const ORIGINE = 'http://localhost:5173';
const IP = '192.168.1.1';
const EMAIL = 'test@example.com';

// Hacheur rapide pour les tests
class HacheurRapide extends HacheurMotDePasse {
	async hacher(motDePasse: string): Promise<string> {
		return `hash:${motDePasse}`;
	}
	async verifier(empreinte: string, motDePasse: string): Promise<boolean> {
		return `hash:${motDePasse}` === empreinte;
	}
}

// Classe de test pour accéder aux méthodes privées via interface
class MagicLinkTestable extends MagicLink {
	constructor(
		comptes: Comptes,
		jetons: JetonsEmail,
		courrier: CourrierJournal,
		base: any,
		maintenant: () => number = Date.now
	) {
		super(comptes, jetons, courrier, base as never, maintenant);
	}
	
	// Expose la méthode privée pour les tests
	usernameDisponible(base: string): string {
		// @ts-ignore - accès à la méthode privée
		return this.#usernameDisponible(base);
	}
	
	ilYAUneHeure(): number {
		// @ts-ignore - accès à la méthode privée
		return this.#ilYAUneHeure();
	}
	
	// Pour accéder à jetons
	getJetons(): JetonsEmail {
		// @ts-ignore
		return this.jetons;
	}
	
	// Pour accéder à comptes
	getComptes(): Comptes {
		// @ts-ignore
		return this.comptes;
	}
}

async function monter() {
	const { base, hacheur } = ouvrirBaseTest();
	const comptes = new Comptes(base, '', hacheur);
	const jetons = new JetonsEmail(base);
	const courrier = new CourrierJournal('');
	
	// Utiliser une Date.now fixe pour les tests coordinating time
	const maintenant = () => 1000000;
	
	return {
		magicLink: new MagicLinkTestable(comptes, jetons, courrier, base, maintenant),
		comptes,
		jetons,
		courrier,
		base,
		hacheur,
		maintenant
	};
}

describe('MagicLink', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	it('envoie un lien magique pour un nouvel email', async () => {
		const { magicLink, courrier } = monter();
		const resultat = await magicLink.demander(EMAIL, ORIGINE, IP);

		expect(resultat.envoye).toBe(true);
		expect(resultat.email).toBe(normaliserEmail(EMAIL));
		expect(courrier.envoyes).toHaveLength(1);
		expect(courrier.envoyes[0].sujet).toBe('RSSResume : votre lien de connexion');
		expect(courrier.envoyes[0].texte).toContain(ORIGINE);
		expect(courrier.envoyes[0].texte).toContain('/magic-link/');
	});

	it('envoie un lien magique pour un email existant', async () => {
		const { magicLink, comptes, courrier } = monter();
		// Créer un compte existant avec mot de passe
		await comptes.creer(EMAIL, 'testuser', 'password123', {});
		
		const resultat = await magicLink.demander(EMAIL, ORIGINE, IP);

		expect(resultat.envoye).toBe(true);
		expect(courrier.envoyes).toHaveLength(1);
	});

	it('réponse identique pour email connu et inconnu', async () => {
		const { magicLink, comptes, courrier } = monter();
		// Créer un compte existant
		await comptes.creer(EMAIL, 'testuser', 'password123', {});
		
		// Demander pour l'email existant
		const resultat1 = await magicLink.demander(EMAIL, ORIGINE, IP);
		courrier.envoyes = [];
		
		// Demander pour un email inconnu
		const resultat2 = await magicLink.demander('unknown@example.com', ORIGINE, IP);

		// Les deux doivent dire envoye: true
		expect(resultat1.envoye).toBe(true);
		expect(resultat2.envoye).toBe(true);
	});

	it('limite à 5 demandes par heure et par email', async () => {
		const { magicLink } = monter();
		
		// 5 demandes OK
		for (let i = 0; i < 5; i++) {
			await magicLink.demander(EMAIL, ORIGINE, IP);
		}
		
		// 6e demande refusée
		let erreur: Error | undefined;
		try {
			await magicLink.demander(EMAIL, ORIGINE, IP);
		} catch (e) {
			erreur = e as Error;
		}
		
		expect(erreur).toBeInstanceOf(ErreurMagicLink);
		expect((erreur as ErreurMagicLink).raison).toBe('limite');
	});

	it('limite à 5 demandes par heure et par IP', async () => {
		const { magicLink } = monter();
		
		// 5 demandes OK avec des emails différents
		for (let i = 0; i < 5; i++) {
			await magicLink.demander(`test${i}@example.com`, ORIGINE, IP);
		}
		
		// 6e demande refusée
		let erreur: Error | undefined;
		try {
			await magicLink.demander('test6@example.com', ORIGINE, IP);
		} catch (e) {
			erreur = e as Error;
		}
		
		expect(erreur).toBeInstanceOf(ErreurMagicLink);
		expect((erreur as ErreurMagicLink).raison).toBe('limite');
	});

	it('crée un compte sans mot de passe à la première demande', async () => {
		const { magicLink, comptes } = monter();
		
		// Demander un lien pour un nouvel email
		const resultat = await magicLink.demander(EMAIL, ORIGINE, IP);
		
		// Vérifier qu'un compte a été créé
		const utilisateur = comptes.parEmail(normaliserEmail(EMAIL));
		expect(utilisateur).not.toBeNull();
		expect(utilisateur?.confirme).toBe(false);
	});

	it('valide un jeton et retourne l\'utilisateur', async () => {
		const { magicLink, jetons } = monter();
		
		// Demander un lien - cela crée un compte
		const { email } = await magicLink.demander(EMAIL, ORIGINE, IP);
		
		// Récupérer l'utilisateur créé
		const utilisateur = magicLink.getComptes().parEmail(email);
		if (!utilisateur) {
			throw new Error('Utilisateur non trouvé après demande');
		}
		
		// Créer un jeton manuellement pour ce test
		const jetonBrut = jetons.emettre(utilisateur.id, utilisateur.email, 'magic-link', DUREE_MAGIC_LINK_MS);
		
		// Valider le jeton
		const valide = magicLink.valider(jetonBrut);
		
		expect(valide).not.toBeNull();
		expect(valide?.email).toBe(email);
	});

	it('un jeton utilisé ne peut plus être utilisé', async () => {
		const { magicLink, jetons } = monter();
		
		// Demander un lien
		const { email } = await magicLink.demander(EMAIL, ORIGINE, IP);
		
		// Récupérer l'utilisateur
		const utilisateur = magicLink.getComptes().parEmail(email);
		if (!utilisateur) {
			throw new Error('Utilisateur non trouvé');
		}
		
		// Créer un jeton
		const jetonBrut = jetons.emettre(utilisateur.id, utilisateur.email, 'magic-link', DUREE_MAGIC_LINK_MS);
		
		// Valider le jeton une première fois
		const valide1 = magicLink.valider(jetonBrut);
		expect(valide1).not.toBeNull();
		
		// Deuxième validation doit échouer (jeton consommé)
		const valide2 = magicLink.valider(jetonBrut);
		expect(valide2).toBeNull();
	});

	it('une nouvelle demande invalide les jetons précédents pour la même adresse', async () => {
		const { magicLink, jetons } = monter();
		
		// Première demande
		const { email: email1 } = await magicLink.demander(EMAIL, ORIGINE, IP);
		const utilisateur = magicLink.getComptes().parEmail(email1);
		if (!utilisateur) throw new Error('Utilisateur non trouvé');
		
		// Créer un premier jeton
		const jeton1 = jetons.emettre(utilisateur.id, utilisateur.email, 'magic-link', DUREE_MAGIC_LINK_MS);
		
		// Deuxième demande (invalide la première)
		await magicLink.demander(EMAIL, ORIGINE, IP);
		
		// Le premier jeton ne doit plus être valide (objet toujours là mais revoqué)
		// En fait, revoquerTous supprime les jetons précédents, donc lire doit retourner null
		// ou un jeton qui n'est plus dans la base
		const lu = jetons.lire(jeton1);
		
		// Le jeton a été revoqué, donc lu doit être null
		expect(lu).toBeNull();
	});

	it('confirme le compte à la validation du magic-link', async () => {
		const { magicLink, jetons } = monter();
		
		// Demander un lien créera un compte non confirmé
		const { email } = await magicLink.demander(EMAIL, ORIGINE, IP);
		
		const utilisateurAvant = magicLink.getComptes().parEmail(email);
		expect(utilisateurAvant).not.toBeNull();
		expect(utilisateurAvant?.confirme).toBe(false);
		
		// Valider le jeton
		const utilisateur = magicLink.getComptes().parEmail(email);
		if (!utilisateur) throw new Error('Utilisateur non trouvé');
		
		const jetonBrut = jetons.emettre(utilisateur.id, utilisateur.email, 'magic-link', DUREE_MAGIC_LINK_MS);
		magicLink.valider(jetonBrut);
		
		// Le compte doit maintenant être confirmé
		const utilisateurApres = magicLink.getComptes().parEmail(email);
		expect(utilisateurApres?.confirme).toBe(true);
	});

	it('génère un username disponible', async () => {
		const { magicLink } = monter();
		
		// Tester la génération de username
		const username = (magicLink as unknown as MagicLinkTestable).usernameDisponible('test');
		
		expect(username).toBe('test');
	});

	it('génère un username avec suffixe si le premier est pris', async () => {
		const { magicLink, comptes } = monter();
		
		// Créer un compte avec username 'test'
		await comptes.creer('test@ex1.com', 'test', 'password123', {});
		
		// Le username suivant doit être 'test1'
		const username = (magicLink as unknown as MagicLinkTestable).usernameDisponible('test');
		
		expect(username).toBe('test1');
	});
});
