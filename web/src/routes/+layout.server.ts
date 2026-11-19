import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ locals }) => {
	return { utilisateur: locals.utilisateur?.pourPage() ?? null };
};
