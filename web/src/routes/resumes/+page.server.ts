import { redirect } from '@sveltejs/kit';
import { exigerConnexion } from '#lib/server/garde.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	const utilisateur = exigerConnexion(locals.utilisateur, url);
	redirect(303, `/resumes/${encodeURIComponent(utilisateur.username)}`);
};
