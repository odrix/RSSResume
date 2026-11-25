/**
 * Les jetons des liens de confirmation : 256 bits aléatoires dans l'email, leur empreinte
 * SHA-256 en base, valables 24 heures et une seule fois.
 *
 * Même parti que les sessions : une copie de la base ne permet de confirmer aucune adresse.
 */

import { createHash, randomBytes } from 'node:crypto';
import type { DatabaseSync } from 'node:sqlite';

export const DUREE_JETON_EMAIL_MS = 24 * 60 * 60 * 1000;

/** Un lien de réinitialisation ouvre le compte à qui le détient : il vit une heure, le
 * temps de lire son email, pas une journée comme une simple confirmation d'adresse. */
export const DUREE_REINITIALISATION_MS = 60 * 60 * 1000;

/** Ce qu'un lien confirme : l'adresse d'un compte qui s'inscrit, un destinataire ajouté
 * dans « Mon profil », une demande de nouveau mot de passe, une nouvelle adresse, ou un lien magique. */
export type ObjetJeton = 'inscription' | 'destinataire' | 'reinitialisation' | 'adresse' | 'magic-link';

/** Durée spécifique pour les liens magiques : 15 minutes, contre 24h pour les confirmations. */
export const DUREE_MAGIC_LINK_MS = 15 * 60 * 1000;

export interface JetonLu {
	compteId: number;
	email: string;
	objet: ObjetJeton;
}

/** Un lien qui ne confirme rien : inconnu, expiré, déjà utilisé, ou une API indisponible. */
export class ErreurConfirmation extends Error {}

export const LIEN_INVALIDE = 'Ce lien de confirmation est invalide, expiré ou déjà utilisé.';

/** Le lien mène à une page qui demande un clic, pas à une action : les antivirus de
 * messagerie ouvrent les liens des emails, et une confirmation par simple GET serait
 * consommée par eux. */
export function lienConfirmation(origine: string, jeton: string): string {
	return `${origine.replace(/\/+$/, '')}/confirmer/${jeton}`;
}

/** Même parti que la confirmation : la page demande le nouveau mot de passe, l'ouvrir ne
 * consomme rien. */
export function lienReinitialisation(origine: string, jeton: string): string {
	return `${origine.replace(/\/+$/, '')}/reinitialiser/${jeton}`;
}

/** Le lien magique mène à une page de confirmation : ouvrir le lien (GET) ne doit pas
 * consommer le jeton, pour résister aux préchargements des clients mail. */
export function lienMagicLink(origine: string, jeton: string): string {
	return `${origine.replace(/\/+$/, '')}/magic-link/${jeton}`;
}

export class JetonsEmail {
	constructor(
		private readonly base: DatabaseSync,
		private readonly maintenant: () => number = Date.now
	) {}

	/** Un nouveau lien remplace le précédent pour la même adresse et le même objet : seul le
	 * dernier email reçu fonctionne. */
	emettre(compteId: number, email: string, objet: ObjetJeton, dureeMs = DUREE_JETON_EMAIL_MS): string {
		const jeton = randomBytes(32).toString('base64url');
		this.base
			.prepare('DELETE FROM jetons_email WHERE compte_id = ? AND email = ? AND objet = ?')
			.run(compteId, email, objet);
		this.base
			.prepare(
				'INSERT INTO jetons_email (id, compte_id, email, objet, expire_le) VALUES (?, ?, ?, ?, ?)'
			)
			.run(empreinte(jeton), compteId, email, objet, this.maintenant() + dureeMs);
		return jeton;
	}

	/** Lit sans consommer : la confirmation peut échouer (API indisponible) et le lien doit
	 * alors rester utilisable. */
	lire(jeton: string): JetonLu | null {
		const ligne = this.base
			.prepare('SELECT compte_id, email, objet, expire_le FROM jetons_email WHERE id = ?')
			.get(empreinte(jeton)) as
			| { compte_id: number; email: string; objet: ObjetJeton; expire_le: number }
			| undefined;
		if (!ligne || ligne.expire_le <= this.maintenant()) return null;
		return { compteId: ligne.compte_id, email: ligne.email, objet: ligne.objet };
	}

	/** Rend vrai pour le seul appel qui a effacé le jeton : deux envois simultanés du même
	 * lien ne doivent pas valoir deux fois. */
	consommer(jeton: string): boolean {
		const resultat = this.base.prepare('DELETE FROM jetons_email WHERE id = ?').run(empreinte(jeton));
		return Number(resultat.changes) === 1;
	}

	/** Les jetons d'une adresse qui n'est plus en attente : un lien reçu plus tôt ne doit
	 * pas la faire revenir. */
	revoquer(compteId: number, email: string, objet: ObjetJeton): void {
		this.base
			.prepare('DELETE FROM jetons_email WHERE compte_id = ? AND email = ? AND objet = ?')
			.run(compteId, email, objet);
	}

	/** Tous les liens d'un objet pour le compte, quelle que soit l'adresse : un lien envoyé
	 * à une adresse mal tapée ne doit pas survivre à la demande qui la corrige. */
	revoquerTous(compteId: number, ...objets: ObjetJeton[]): void {
		const requete = this.base.prepare('DELETE FROM jetons_email WHERE compte_id = ? AND objet = ?');
		for (const objet of objets) requete.run(compteId, objet);
	}

	purgerExpires(): void {
		this.base.prepare('DELETE FROM jetons_email WHERE expire_le <= ?').run(this.maintenant());
	}
}

function empreinte(jeton: string): string {
	return createHash('sha256').update(jeton).digest('hex');
}
