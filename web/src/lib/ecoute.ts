/**
 * Signaler au site qu'une journée a été écoutée jusqu'au bout, pour la marquer lue.
 *
 * Deux entrées : `signalerEcoute` pour qui connaît déjà la journée — un lecteur qui la garde
 * en mémoire —, et `signalerEcouteTerminee`, à brancher tel quel sur `onended` d'un `<audio>`
 * qui ne connaît que sa source : elle relit la journée dans l'URL du relais audio.
 */

/** `/audio/{username}/{date}/{nom}` : le chemin du relais, seul à porter une journée. */
const CHEMIN_AUDIO = /^\/audio\/([^/]+)\/([^/]+)\/[^/]+$/;

/** Au mieux : un marquage perdu ne vaut pas une erreur sous les yeux de qui vient d'écouter.
 * `keepalive` pour que la requête parte même si la page se ferme à la fin de l'audio. */
export function signalerEcoute(username: string, date: string): void {
	const url = `/resumes/${encodeURIComponent(username)}/${encodeURIComponent(date)}/ecoute`;
	try {
		fetch(url, { method: 'POST', keepalive: true }).catch(() => {});
	} catch {
		// Un fetch absent ou refusé d'emblée : même règle, rien à montrer.
	}
}

export function signalerEcouteTerminee(evenement: Event): void {
	const element = evenement.currentTarget as HTMLMediaElement | null;
	const source = element?.currentSrc;
	if (!source) return;
	// Une source d'une autre origine n'est pas le relais du site, même si son chemin y ressemble.
	const ici = new URL(globalThis.location?.href ?? 'http://local.invalid/');
	let url: URL;
	try {
		url = new URL(source, ici);
	} catch {
		return;
	}
	if (url.origin !== ici.origin) return;
	const trouve = CHEMIN_AUDIO.exec(url.pathname);
	if (!trouve) return;
	try {
		signalerEcoute(decodeURIComponent(trouve[1]), decodeURIComponent(trouve[2]));
	} catch {
		// Un segment mal encodé ne vient pas du relais : rien à signaler.
	}
}
