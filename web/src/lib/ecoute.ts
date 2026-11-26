/**
 * Signaler au site qu'une journée a été écoutée jusqu'au bout, pour la marquer lue.
 *
 * Deux entrées : `signalerEcoute` pour qui connaît déjà la journée — un lecteur qui la garde
 * en mémoire —, et `signalerEcouteTerminee`, à brancher sur `onended` d'un `<audio>` qui ne
 * connaît que sa source : elle relit la journée dans l'URL du relais audio.
 */

/** `/audio/{username}/{date}/{nom}` : le chemin du relais, seul à porter une journée. */
const CHEMIN_AUDIO = /^\/audio\/([^/]+)\/([^/]+)\/[^/]+$/;

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

/** La date marquée, ou `null` si la source n'est pas une journée du relais ou si le marquage
 * a échoué : la page n'a besoin que de savoir quelle carte passer en lue. */
export async function signalerEcouteTerminee(evenement: Event): Promise<string | null> {
	const element = evenement.currentTarget as HTMLMediaElement | null;
	const source = element?.currentSrc;
	if (!source) return null;
	// Une source d'une autre origine n'est pas le relais du site, même si son chemin y ressemble.
	const ici = new URL(globalThis.location?.href ?? 'http://local.invalid/');
	let url: URL;
	try {
		url = new URL(source, ici);
	} catch {
		return null;
	}
	if (url.origin !== ici.origin) return null;
	const trouve = CHEMIN_AUDIO.exec(url.pathname);
	if (!trouve) return null;
	let username: string;
	let date: string;
	try {
		username = decodeURIComponent(trouve[1]);
		date = decodeURIComponent(trouve[2]);
	} catch {
		// Un segment mal encodé ne vient pas du relais : rien à signaler.
		return null;
	}
	return (await signalerEcoute(username, date)) ? date : null;
}
