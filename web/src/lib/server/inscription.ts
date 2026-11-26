/**
 * L'inscription, en deux temps : un compte en attente ici, puis, au clic sur le lien
 * reçu, le profil côté API, l'alerte à l'administrateur et la bienvenue.
 *
 * Le profil n'est créé qu'à la confirmation parce que c'est lui qui fait partir le digest :
 * créé plus tôt, il enverrait chaque matin un email à une adresse que personne n'a prouvé
 * posséder. Jusque-là, le texte saisi et les réglages du métier choisi attendent dans le
 * brouillon du compte.
 */

import type { Passage } from '#lib/journee.js';
import { PROFIL_PAR_DEFAUT, type Gabarit, type ProfilSaisi } from '#lib/profil.js';
import { ErreurApi, type ClientApiResume } from './api-resume.js';
import { CompteExistant, type Brouillon, type Comptes, type Utilisateur } from './comptes.js';
import type { Courrier, Inscrit } from './courrier.js';
import {
	ErreurConfirmation,
	LIEN_INVALIDE,
	lienConfirmation,
	type JetonsEmail
} from './jetons-email.js';
import { erreurEmail, erreurMotDePasse, erreurUsername, normaliserEmail } from './validation.js';

export interface SaisieInscription {
	email: string;
	username: string;
	motDePasse: string;
	prenom: string;
	profil: string;
	/** L'identifiant d'un gabarit, ou `METIER_AUTRE` pour s'en passer. */
	metier: string;
}

/** Le choix de qui ne se reconnaît dans aucun gabarit : son profil n'aura ni axes ni
 * catégories, c'est-à-dire les rubriques par défaut et tout le catalogue, le profil
 * d'avant les gabarits. */
export const METIER_AUTRE = 'autre';

export type ChampInscription = keyof SaisieInscription | 'general';

export class ErreurInscription extends Error {
	constructor(
		readonly champ: ChampInscription,
		message: string
	) {
		super(message);
	}
}

export class Inscription {
	constructor(
		private readonly comptes: Comptes,
		private readonly jetons: JetonsEmail,
		private readonly api: ClientApiResume,
		private readonly courrier: Courrier
	) {}

	/** Crée le compte en attente et envoie le lien. `origine` est l'adresse publique du site,
	 * qui préfixe le lien. */
	async inscrire(saisie: SaisieInscription, origine: string): Promise<Utilisateur> {
		const email = normaliserEmail(saisie.email);
		const verifications: [ChampInscription, string | null][] = [
			['email', erreurEmail(email)],
			['username', erreurUsername(saisie.username)],
			['motDePasse', erreurMotDePasse(saisie.motDePasse)],
			['metier', saisie.metier.trim() ? null : 'Choisissez votre métier, ou « Autre ».']
		];
		for (const [champ, message] of verifications) {
			if (message) throw new ErreurInscription(champ, message);
		}
		if (!this.courrier.disponible) {
			console.error("Inscription refusée : aucun transport d'email configuré (RESEND_API_KEY, MAIL_FROM).");
			throw new ErreurInscription(
				'general',
				"Les inscriptions sont momentanément fermées : l'email de confirmation ne peut pas partir."
			);
		}

		// À la volée : un compte abandonné depuis sept jours libère son adresse et son username.
		this.comptes.purgerNonConfirmes();
		const conflit = this.comptes.conflit(email, saisie.username);
		if (conflit) throw new ErreurInscription(conflit.champ, conflit.message);

		const gabarit = await this.#gabarit(saisie.metier.trim());
		let utilisateur: Utilisateur;
		try {
			utilisateur = await this.comptes.creer(email, saisie.username, saisie.motDePasse, {
				// Sans JavaScript, la zone de texte arrive vide : le texte du gabarit est celui
				// que la personne aurait vu en choisissant son métier.
				profil: saisie.profil.trim() || (gabarit?.profil ?? PROFIL_PAR_DEFAUT),
				prenom: saisie.prenom.trim(),
				gabarit: gabarit && {
					metier: gabarit.metier,
					libelle: gabarit.libelle,
					stack: gabarit.stack,
					securite: gabarit.securite,
					axes: gabarit.axes,
					categories: gabarit.categories
				}
			});
		} catch (erreur) {
			if (erreur instanceof CompteExistant) throw new ErreurInscription(erreur.champ, erreur.message);
			throw erreur;
		}

		if (!(await this.#envoyerLien(utilisateur, origine))) {
			// Un compte dont le lien n'est jamais parti ne pourrait pas être activé.
			this.comptes.supprimer(utilisateur.id);
			throw new ErreurInscription(
				'general',
				"L'email de confirmation n'a pas pu être envoyé. Réessayez dans quelques minutes."
			);
		}
		return utilisateur;
	}

	/** Renvoie un lien à un compte en attente. Silencieux dans tous les cas : la réponse ne
	 * doit pas dire si l'adresse a un compte. */
	async renvoyer(email: string, origine: string): Promise<void> {
		const utilisateur = this.comptes.parEmail(email);
		if (!utilisateur || utilisateur.confirme) return;
		await this.#envoyerLien(utilisateur, origine);
	}

	/** Crée le profil, confirme le compte, prévient l'administrateur et souhaite la
	 * bienvenue. Le jeton n'est consommé qu'une fois le profil créé : une API indisponible
	 * laisse le lien utilisable. `origine` préfixe les liens de la bienvenue. */
	async confirmer(jeton: string, origine: string): Promise<Utilisateur> {
		const lu = this.jetons.lire(jeton);
		const compte = lu?.objet === 'inscription' ? this.comptes.parId(lu.compteId) : null;
		if (!lu || !compte || compte.email !== lu.email) throw new ErreurConfirmation(LIEN_INVALIDE);
		if (compte.confirme) {
			this.jetons.consommer(jeton);
			return compte;
		}

		const brouillon = this.comptes.brouillon(compte.id);
		const gabarit = brouillon.gabarit;
		const saisie: ProfilSaisi = {
			// Le défaut couvre les comptes inscrits avant les gabarits, au brouillon parfois vide.
			profil: brouillon.profil || PROFIL_PAR_DEFAUT,
			stack: gabarit?.stack ?? [],
			// L'adresse du compte vient d'être prouvée : c'est le premier destinataire.
			email: [compte.email],
			prenom: brouillon.prenom,
			securite: gabarit?.securite ?? 'exploitant'
		};
		if (gabarit) {
			// Sans gabarit, les clés restent absentes : axes par défaut et tout le catalogue.
			saisie.axes = gabarit.axes;
			saisie.categories = gabarit.categories;
		}
		try {
			await this.api.creerProfil(compte.username, saisie);
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			if (erreur.statut === 409) {
				console.error(`Confirmation de ${compte.username} : le profil existe déjà côté API.`);
				throw new ErreurConfirmation(
					"Ce nom d'utilisateur est déjà utilisé par le service de résumé. Contactez l'administrateur."
				);
			}
			throw new ErreurConfirmation(erreur.message);
		}

		const premiere = this.comptes.confirmer(compte.id);
		this.jetons.consommer(jeton);
		// La base dit qui a fait passer le compte en confirmé, pas le contrôle plus haut, lu
		// avant l'appel à l'API : ce qui ne doit partir qu'une fois dépend d'elle seule.
		if (premiere) {
			const inscrit = { username: compte.username, email: compte.email };
			await this.courrier.alerterAdmin(inscrit);
			await this.#souhaiterBienvenue(inscrit, brouillon, origine);
		}
		return this.comptes.parId(compte.id)!;
	}

	/** Le gabarit choisi, ou `null` pour « Autre ». Lu de l'API à l'inscription même, pour
	 * que le brouillon garde ce que la page vient d'afficher et rien d'imaginé côté site. */
	async #gabarit(metier: string): Promise<Gabarit | null> {
		if (metier === METIER_AUTRE) return null;
		let gabarits: Gabarit[];
		try {
			gabarits = await this.api.listerGabarits();
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			throw new ErreurInscription(
				'general',
				'Service momentanément indisponible : votre métier ne peut pas être vérifié. Réessayez dans quelques minutes, ou choisissez « Autre ».'
			);
		}
		const gabarit = gabarits.find((candidat) => candidat.metier === metier);
		if (!gabarit) throw new ErreurInscription('metier', "Ce métier n'est pas proposé. Choisissez-en un dans la liste.");
		return gabarit;
	}

	/** Un échec d'envoi ne défait rien : le compte et son profil sont là, le premier digest
	 * partira quand même. Il n'y a pas de relance, le message n'est qu'un accueil. */
	async #souhaiterBienvenue(inscrit: Inscrit, brouillon: Brouillon, origine: string): Promise<void> {
		const gabarit = brouillon.gabarit;
		const envoye = await this.courrier.souhaiterBienvenue(inscrit, {
			prenom: brouillon.prenom,
			libelleMetier: gabarit?.libelle ?? null,
			categories: gabarit?.categories ?? null,
			passage: await this.#passage(),
			origine
		});
		if (!envoye) console.error(`Bienvenue de ${inscrit.username} non envoyée ; pas de relance.`);
	}

	/** L'heure du passage, ou `null` : une API muette n'empêche pas d'accueillir. */
	async #passage(): Promise<Passage | null> {
		try {
			return await this.api.lirePassage();
		} catch (erreur) {
			if (!(erreur instanceof ErreurApi)) throw erreur;
			return null;
		}
	}

	#envoyerLien(utilisateur: Utilisateur, origine: string): Promise<boolean> {
		const jeton = this.jetons.emettre(utilisateur.id, utilisateur.email, 'inscription');
		return this.courrier.confirmerInscription(
			{ username: utilisateur.username, email: utilisateur.email },
			lienConfirmation(origine, jeton)
		);
	}
}
