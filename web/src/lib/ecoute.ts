/**
 * Signaler au site qu'une journée a été écoutée jusqu'au bout, pour la marquer lue.
 *
 * Le lecteur du layout annonce la fin d'une écoute ; `marquerLesEcoutes` en fait un marquage.
 * L'abonnement vit dans le layout et non dans une page : une écoute lancée depuis la liste se
 * termine souvent ailleurs, et doit compter quand même.
 */

import type { LecteurAudio } from './lecteur.svelte.js';

/** Vrai si le site a bien marqué la journée : la page peut alors l'afficher lue sans
 * attendre un rechargement.
 *
 * Jamais d'exception : un marquage perdu ne vaut pas une erreur sous les yeux de qui vient
 * d'écouter. `keepalive` pour que la requête parte même si la page se ferme à la fin de l'audio. */
export async function signalerEcoute(username: string, date: string): Promise<boolean> {
	const url = `/resumes/${encodeURIComponent(username)}/${encodeURIComponent(date)}/ecoute`;
	try {
		const reponse = await fetch(url, { method: 'POST', keepalive: true });
		return reponse.ok;
	} catch {
		return false;
	}
}

/** Seule une piste qui couvre la journée entière la marque : finir une catégorie n'est pas
 * avoir écouté la journée. Le site refuse de son côté tout profil qui n'est pas celui de la
 * session ; rien à filtrer ici. Rend le désabonnement. */
export function marquerLesEcoutes(lecteur: Pick<LecteurAudio, 'surEcouteTerminee'>): () => void {
	return lecteur.surEcouteTerminee((piste) => {
		if (piste.journeeEntiere) void signalerEcoute(piste.username, piste.date);
	});
}
