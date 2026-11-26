/**
 * Le vote « utile / pas utile » sur une journée : ce que le navigateur et le serveur partagent.
 *
 * Les valeurs sont celles de `rssresume/retours.py`, et la borne du commentaire aussi : le
 * formulaire la pose en `maxlength`, le serveur du site la revérifie, et l'API fait foi.
 */

export type Avis = 'utile' | 'pas_utile';

export const AVIS: readonly Avis[] = ['utile', 'pas_utile'];

export const LIBELLES_AVIS: Record<Avis, string> = {
	utile: 'Utile',
	pas_utile: 'Pas utile'
};

/** En caractères, points de code, comme Python les compte : un emoji vaut un. */
export const LONGUEUR_MAX_COMMENTAIRE = 2000;

export function estAvis(valeur: unknown): valeur is Avis {
	return valeur === 'utile' || valeur === 'pas_utile';
}
