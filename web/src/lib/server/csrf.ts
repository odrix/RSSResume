/**
 * La protection CSRF du site, réécrite ici parce qu'il fallait une exception.
 *
 * SvelteKit refuse en 403 tout envoi de formulaire venu d'une autre origine, avant même le
 * hook `handle`. Le désabonnement en un clic de Gmail et Yahoo (RFC 8058) est justement
 * cela : un POST `application/x-www-form-urlencoded`, corps `List-Unsubscribe=One-Click`,
 * envoyé par le client mail sans `Origin`. Le seul réglage de SvelteKit qui le laisse
 * passer est `csrf.trustedOrigins: ['*']`, qui lève la protection partout ; elle est donc
 * rétablie ici, à l'identique, pour toutes les routes sauf celle-là.
 *
 * La règle est celle de `@sveltejs/kit/src/runtime/server/csrf.js` : une méthode qui
 * modifie, un corps qu'un formulaire HTML sait envoyer (ou pas de corps typé du tout), et
 * une origine absente ou différente de celle du site. Ce que l'exception ouvre ne demande
 * aucune session : le jeton signé du lien est la seule autorisation de la route.
 */

const METHODES_MUTANTES = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Les corps qu'un `<form>` d'un autre site peut envoyer sans pré-vérification CORS, plus
 * celui des formulaires binaires de SvelteKit, que sa propre règle protège aussi. */
const TYPES_FORMULAIRE = new Set([
	'application/x-www-form-urlencoded',
	'multipart/form-data',
	'text/plain',
	'application/x-sveltekit-formdata'
]);

/** La seule route ouverte aux POST d'ailleurs : la page du lien de désabonnement. */
const MOTIF_DESABONNEMENT = /^\/desabonnement\/[^/]+\/?$/;

function estFormulaire(request: Request): boolean {
	const type = request.headers.get('content-type');
	if (!type) return true;
	return TYPES_FORMULAIRE.has(type.split(';', 1)[0].trim().toLowerCase());
}

/** Vrai pour un envoi de formulaire d'une autre origine, à refuser en 403, sauf le POST
 * du désabonnement en un clic, qui vient d'un client mail et n'a pas d'origine. */
export function postIntersiteInterdit(request: Request, url: URL): boolean {
	if (!METHODES_MUTANTES.has(request.method)) return false;
	if (!estFormulaire(request)) return false;
	if (request.headers.get('origin') === url.origin) return false;
	return !(request.method === 'POST' && MOTIF_DESABONNEMENT.test(url.pathname));
}
