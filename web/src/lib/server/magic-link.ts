/**
 * La connexion par magic-link : un lien envoyé par email qui ouvre une session.
 *
 * Un compte peut être créé sans mot de passe (ajouté ensuite dans _Compte_).
 * Le jeton est valable 15 minutes, à usage unique ; une nouvelle demande invalide les précédents.
 */

import type { DatabaseSync } from 'node:sqlite';
import type { Comptes, Utilisateur } from './comptes.js';
import type { Courrier } from './courrier.js';
import { DUREE_MAGIC_LINK_MS, type JetonsEmail, lienMagicLink } from './jetons-email.js';
import { normaliserEmail } from './validation.js';

/** Ce qui peut aller de travers avec un magic-link. */
export class ErreurMagicLink extends Error {
	constructor(readonly raison: 'limite' | 'courrier-indisponible') {
		super(raison === 'limite' ? 'Trop de demandes. Réessayez dans une heure.' : 'Les emails ne peuvent pas partir pour le moment.');
	}
}

/** Le résultat d'une demande de magic-link. */
export interface ResultatDemande {
	/** Vrai si un email a été envoyé. Faux ne veut pas dire un échec : la réponse est la même
	 * pour un email connu et inconnu, pour éviter l'énumération de comptes. */
	envoye: boolean;
	email: string;
}

/** La logique métier du magic-link. Un compte préféré peut demander un jeton ; les demandeurs
 * anonymes en reçoivent, tendis un stipulé connu l'adresse d'un email. */
export class MagicLink {
	constructor(
		private readonly comptes: Comptes,
		private readonly jetons: JetonsEmail,
		private readonly courrier: Courrier,
		private readonly base: DatabaseSync,
		private readonly maintenant: () => number = Date.now
	) {}

	/** Demande un lien magique pour une adresse.
	 *
	 * - Si l'adresse a déjà un compte (confirmed ou non), envoie un lien pour ce compte.
	 * - Si l'adresse n'a pas de compte, crée un compte sans mot de passe en attente.
	 * - Réponse identique dans tous les cas : impossible de savoir si l'adresse existe.
	 * - Une nouvelle demande invalide toutes les précédentes pour cette adresse.
	 * - Limite : 5 demandes par heure et par email, et par IP.
	 */
	async demander(email: string, origine: string, ip: string): Promise<ResultatDemande> {
		const emailNormalise = normaliserEmail(email);

		// Limite par email
		const demandeIP = this.base
			.prepare('SELECT COUNT(*) AS nombre FROM magic_link_demandes WHERE ip = ? AND demande_le >= ?')
			.get(ip, this.#ilYAUneHeure()) as { nombre: number };
		if (demandeIP.nombre >= 5) {
			throw new ErreurMagicLink('limite');
		}

		const demandeEmail = this.base
			.prepare('SELECT COUNT(*) AS nombre FROM magic_link_demandes WHERE email = ? AND demande_le >= ?')
			.get(emailNormalise, this.#ilYAUneHeure()) as { nombre: number };
		if (demandeEmail.nombre >= 5) {
			throw new ErreurMagicLink('limite');
		}

		if (!this.courrier.disponible) {
			throw new ErreurMagicLink('courrier-indisponible');
		}

		// Trouver ou créer le compte
		let utilisateur = this.comptes.parEmail(emailNormalise);
		if (!utilisateur) {
			// Créer un compte sans mot de passe. L'email est l'identifiant.
			// Pour le username, on utilise une version normalisée de l'email (partie avant @)
			// ou l'email complète si c'est nécessaire. On va générer un username unique.
			const localPart = emailNormalise.split('@')[0];
			const username = this.#usernameDisponible(localPart);
			utilisateur = await this.comptes.creer(emailNormalise, username, null);
		}

		// Invalider les jetons précédents pour cette adresse
		this.jetons.revoquerTous(utilisateur.id, 'magic-link');

		// Émettre un nouveau jeton
		const jeton = this.jetons.emettre(utilisateur.id, emailNormalise, 'magic-link', DUREE_MAGIC_LINK_MS);
		
		// Enregistrer la demande pour le rate limiting
		this.base
			.prepare('INSERT INTO magic_link_demandes (email, ip, demande_le) VALUES (?, ?, ?)')
			.run(emailNormalise, ip, this.maintenant());

		// Envoyer l'email
		const likn = lienMagicLink(origine, jeton);
		const envoye = await this.courrier.envoyerLienMagique(emailNormalise, likn);

		return { envoye, email: emailNormalise };
	}

	/** Valide un jeton de magic-link et retourne l'utilisateur.
	 * Le jeton est consommé seulement si la validation réussit.
	 */
	valider(jeton: string): Utilisateur | null {
		const lu = this.jetons.lire(jeton);
		if (!lu || lu.objet !== 'magic-link') return null;

		const utilisateur = this.comptes.parId(lu.compteId);
		if (!utilisateur || utilisateur.email !== lu.email) return null;

		// Consommer le jeton
		this.jetons.consommer(jeton);

		// Confirmer le compte s'il ne l'était pas (cas de création via magic-link)
		if (!utilisateur.confirme) {
			this.comptes.confirmer(utilisateur.id);
		}

		return utilisateur;
	}

	/** Génère un username disponible à partir d'une base. */
	#usernameDisponible(base: string): string {
		let candidate = base;
		let suffixe = 0;
		
		while (true) {
			const existing = this.comptes.parEmail(candidate + '@example.com');
			// Vérifier aussi par username directement
			const conflit = this.comptes.conflit(candidate + '@example.com', candidate);
			if (!conflit) {
				// Vérifier aussi si le username existe déjà
				const usernameExists = this.base
					.prepare('SELECT 1 FROM comptes WHERE username = ?')
					.get(candidate) as { 1: number } | undefined;
				if (!usernameExists) {
					return candidate;
				}
			}
			// Essayer avec un suffixe
			suffixe++;
			candidate = `${base}${suffixe}`;
		}
	}

	/** Date il y a 1 heure. */
	#ilYAUneHeure(): number {
		return this.maintenant() - 60 * 60 * 1000;
	}
}
