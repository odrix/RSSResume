import { contexte } from '#lib/server/contexte.js';
import type { PageServerLoad } from './$types';

/** Sans garde : la page se lit avant de créer un compte, et après l'avoir perdu. */
export const load: PageServerLoad = () => {
	return { contact: contexte().contact };
};
