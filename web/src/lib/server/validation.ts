/**
 * Les règles d'un compte. Elles rendent un message, pas un booléen : c'est ce message que
 * le formulaire affiche, et l'écrire à côté de la règle évite qu'ils divergent.
 */

/** Le même motif que l'appli de résumé : le username nomme aussi le profil côté API. */
export const MOTIF_USERNAME = /^[a-z0-9][a-z0-9_-]{1,31}$/;
export const LONGUEUR_MIN_MOT_DE_PASSE = 12;
/** Au-delà, Argon2 travaille pour rien et la requête devient un moyen de charger le serveur. */
export const LONGUEUR_MAX_MOT_DE_PASSE = 256;

export function erreurUsername(username: string): string | null {
	if (!MOTIF_USERNAME.test(username)) {
		return "Le nom d'utilisateur fait 2 à 32 caractères : minuscules, chiffres, « _ » ou « - », sans commencer par « _ » ni « - ».";
	}
	return null;
}

export function erreurMotDePasse(motDePasse: string): string | null {
	// Compté en points de code : un emoji est un caractère pour la personne qui le tape.
	const longueur = [...motDePasse].length;
	if (longueur < LONGUEUR_MIN_MOT_DE_PASSE) {
		return `Le mot de passe fait au moins ${LONGUEUR_MIN_MOT_DE_PASSE} caractères.`;
	}
	if (longueur > LONGUEUR_MAX_MOT_DE_PASSE) {
		return `Le mot de passe fait au plus ${LONGUEUR_MAX_MOT_DE_PASSE} caractères.`;
	}
	return null;
}

/** Volontairement lâche : la seule preuve qu'une adresse existe est d'y écrire. */
export function erreurEmail(email: string): string | null {
	if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
		return "L'adresse email n'est pas valide.";
	}
	return null;
}

export function normaliserEmail(email: string): string {
	return email.trim().toLowerCase();
}
