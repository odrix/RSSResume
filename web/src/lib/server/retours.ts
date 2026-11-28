/**
 * Les retours « utile / pas utile » sur une journée : par le lien de la lettre, sans
 * session, et depuis la page des résumés, pour qui est connecté.
 *
 * Le lien de la lettre se relaie comme celui du désabonnement : signé par le travailleur, le
 * site ne sait pas le vérifier et n'a pas à le savoir. Le vote du site, lui, passe par
 * l'API au nom du profil, après le contrôle d'accès fait ici, l'API n'a qu'un jeton, celui
 * du site, et rend n'importe quel profil à qui le porte.
 */

import { estAvis, LONGUEUR_MAX_COMMENTAIRE, type Avis } from '#lib/retour.js';
import { ErreurApi, type ClientApiResume, type LectureRetour, type Retour } from './api-resume.js';
import { type Comptes, type Utilisateur } from './comptes.js';
import { MOTIF_USERNAME } from './validation.js';

export const LIEN_RETOUR_INVALIDE = 'Ce lien de vote est invalide.';

const MOTIF_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Les champs signés, séparés par des points, dans l'alphabet d'URL. Le jeton de vote a une
 * longueur fixe, version, identifiant, date, signature, d'où une borne serrée. */
const MOTIF_JETON = /^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$/;
const LONGUEUR_MAX_JETON = 256;

function jetonPlausible(jeton: string): boolean {
	return jeton.length <= LONGUEUR_MAX_JETON && MOTIF_JETON.test(jeton);
}

/** Un vote qui n'a pas pu se faire, avec le message à montrer. */
export class ErreurRetour extends Error {}

export interface SaisieRetour {
	avis: Avis;
	commentaire: string;
}

/** Le vote d'un formulaire, vérifié comme l'API le vérifiera.
 *
 * Revérifié ici malgré le `maxlength` du formulaire : un navigateur compte en unités UTF-16,
 * l'API en points de code, et un formulaire se contourne. Compter comme l'API, un emoji
 * vaut un, évite de refuser ici ce qu'elle accepterait. */
export function saisieRetour(form: FormData): SaisieRetour {
	const avis = form.get('avis');
	if (!estAvis(avis)) throw new ErreurRetour('Choisissez « Utile » ou « Pas utile ».');
	const commentaire = String(form.get('commentaire') ?? '')
		.replace(/\r\n?/g, '\n')
		.trim();
	if ([...commentaire].length > LONGUEUR_MAX_COMMENTAIRE) {
		throw new ErreurRetour(`Le commentaire dépasse ${LONGUEUR_MAX_COMMENTAIRE} caractères.`);
	}
	return { avis, commentaire };
}

export class Retours {
	/** `comptes` écrit le vote dans la base du site, pour les compteurs de /admin : tout vote
	 * passe par ici, qu'il vienne du lien de la lettre ou de la page des résumés. */
	constructor(
		private readonly api: ClientApiResume,
		private readonly comptes: Comptes
	) {}

	/** Ce que le lien désigne et le vote déjà donné, ou `null` s'il est invalide.
	 *
	 * L'affichage de la page n'appelle que ceci : un antivirus de messagerie qui ouvre le
	 * lien ne doit pas voter à la place de la personne. */
	async lireLien(jeton: string): Promise<LectureRetour | null> {
		if (!jetonPlausible(jeton)) return null;
		try {
			return await this.api.lireRetourParLien(jeton);
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) return null;
			if (erreur instanceof ErreurApi) throw new ErreurRetour(erreur.message);
			throw erreur;
		}
	}

	/** Le vote du lien de la lettre. Lien invalide ou saisie refusée : `ErreurRetour`. */
	async voterParLien(jeton: string, saisie: SaisieRetour): Promise<LectureRetour> {
		if (!jetonPlausible(jeton)) throw new ErreurRetour(LIEN_RETOUR_INVALIDE);
		try {
			const lecture = await this.api.voterParLien(jeton, saisie.avis, saisie.commentaire);
			this.comptes.noterRetour(lecture.username, lecture.jour, saisie.avis);
			return lecture;
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) throw new ErreurRetour(LIEN_RETOUR_INVALIDE);
			if (erreur instanceof ErreurApi) throw new ErreurRetour(erreur.message);
			throw erreur;
		}
	}

	/** Le vote du propriétaire sur sa journée, ou `null` : pas de vote, ou pas le sien.
	 *
	 * Le propriétaire seulement, pas l'administrateur : le vote est celui des lecteurs du
	 * profil, et un admin qui consulte la journée d'un autre n'a pas à y voter. */
	async lire(utilisateur: Utilisateur, username: string, date: string): Promise<Retour | null> {
		if (!this.#peutVoter(utilisateur, username, date)) return null;
		try {
			return await this.api.lireRetour(username, date);
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) return null;
			throw erreur;
		}
	}

	/** Le vote du propriétaire, qui remplace le précédent ; `null` pour qui n'est pas le
	 * propriétaire. Saisie refusée par l'API : `ErreurRetour`. */
	async voter(utilisateur: Utilisateur, username: string, date: string, saisie: SaisieRetour): Promise<Retour | null> {
		if (!this.#peutVoter(utilisateur, username, date)) return null;
		try {
			const retour = await this.api.voter(username, date, saisie.avis, saisie.commentaire);
			this.comptes.noterRetour(username, date, saisie.avis);
			return retour;
		} catch (erreur) {
			if (erreur instanceof ErreurApi) throw new ErreurRetour(erreur.message);
			throw erreur;
		}
	}

	/** Les retours les plus récents d'abord. La garde est celle de la page : `exigerAdmin`. */
	lister(): Promise<Retour[]> {
		return this.api.listerRetours();
	}

	#peutVoter(utilisateur: Utilisateur, username: string, date: string): boolean {
		return utilisateur.username === username && MOTIF_USERNAME.test(username) && MOTIF_DATE.test(date);
	}
}
