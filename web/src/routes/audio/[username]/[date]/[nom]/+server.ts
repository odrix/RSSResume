import { contexte } from '#lib/server/contexte.js';
import type { RequestHandler } from './$types';

/** Le contrôle d'accès et le relais sont dans `RelaisAudio`, testés hors de SvelteKit. */
export const GET: RequestHandler = ({ locals, params, request }) => {
	return contexte().relaisAudio.servir(locals.utilisateur, params, request);
};
