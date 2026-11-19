/**
 * Le relais des MP3 : le navigateur ne parle qu'au site, le site parle à l'API avec son jeton.
 *
 * Le flux est recopié tel quel, sans être chargé en mémoire, et l'en-tête `Range` est
 * transmis dans les deux sens : sans réponses 206, un lecteur <audio> ne sait pas avancer
 * dans un fichier qu'il n'a pas fini de télécharger.
 */

import { ErreurApi, type ClientApiResume } from './api-resume.js';
import type { Utilisateur } from './comptes.js';
import { MOTIF_USERNAME } from './validation.js';

export interface CheminAudio {
	username: string;
	date: string;
	nom: string;
}

/** Les en-têtes de l'API qui décrivent le flux ; les autres (serveur, cookies…) restent là-bas. */
const ENTETES_RELAYES = [
	'content-type',
	'content-length',
	'content-range',
	'accept-ranges',
	'etag',
	'last-modified'
];

const MOTIF_DATE = /^\d{4}-\d{2}-\d{2}$/;
/** Un nom de fichier, jamais un chemin : ni « / », ni « .. » en tête. */
const MOTIF_NOM = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.mp3$/;

export class RelaisAudio {
	constructor(private readonly api: ClientApiResume) {}

	async servir(
		utilisateur: Utilisateur | null,
		chemin: CheminAudio,
		requete: Request
	): Promise<Response> {
		if (!utilisateur) return texte(401, 'Connexion requise.');
		// 404 et non 403 pour qui n'est pas le propriétaire : la réponse ne dit pas si le
		// username existe.
		if (!utilisateur.peutConsulter(chemin.username) || !cheminValide(chemin)) {
			return texte(404, 'Audio introuvable.');
		}

		let amont: Response;
		try {
			amont = await this.api.audio(chemin.username, chemin.date, chemin.nom, {
				range: requete.headers.get('range'),
				signal: requete.signal
			});
		} catch (erreur) {
			if (erreur instanceof ErreurApi && erreur.introuvable) return texte(404, 'Audio introuvable.');
			console.error('Relais audio :', erreur);
			return texte(502, 'Le service de résumé ne répond pas.');
		}

		const entetes = new Headers();
		for (const nom of ENTETES_RELAYES) {
			const valeur = amont.headers.get(nom);
			if (valeur !== null) entetes.set(nom, valeur);
		}
		if (amont.status !== 416) entetes.set('content-type', 'audio/mpeg');
		entetes.set('accept-ranges', 'bytes');
		// Privé : le fichier est derrière une session, aucun cache partagé ne doit le garder.
		entetes.set('cache-control', 'private, max-age=3600');
		entetes.set('x-content-type-options', 'nosniff');
		return new Response(amont.body, { status: amont.status, headers: entetes });
	}
}

function cheminValide({ username, date, nom }: CheminAudio): boolean {
	return MOTIF_USERNAME.test(username) && MOTIF_DATE.test(date) && MOTIF_NOM.test(nom);
}

function texte(statut: number, message: string): Response {
	return new Response(message, {
		status: statut,
		headers: { 'content-type': 'text/plain; charset=utf-8' }
	});
}
