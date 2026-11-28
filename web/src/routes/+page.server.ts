import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { redirect } from '@sveltejs/kit';

import type { PageServerLoad } from './$types';

/**
 * L'extrait de lettre de démonstration est un fichier versionné, lu sur le disque : jamais
 * tiré de l'API ni d'une session, la page d'accueil se lit sans compte. En développement il
 * vit dans `static/` ; en production le build le copie sous `build/client/`.
 */
function lireExtraitLettre(): string {
	for (const chemin of ['static/exemple/lettre.txt', 'build/client/exemple/lettre.txt']) {
		const absolu = resolve(chemin);
		if (existsSync(absolu)) return readFileSync(absolu, 'utf-8');
	}
	throw new Error("Extrait de démonstration introuvable : static/exemple/lettre.txt");
}

export const load: PageServerLoad = ({ locals }) => {
	if (locals.utilisateur) redirect(303, '/resumes');
	// Le lecteur audio pointe le fichier statique servi tel quel à la racine du site.
	return { extraitLettre: lireExtraitLettre(), audioExemple: '/exemple/extrait.mp3' };
};
