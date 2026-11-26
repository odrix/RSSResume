/**
 * Un environnement de test Node dont les modules sont compilés pour le client.
 *
 * L'environnement `node` des tests transforme tout en mode serveur, où Svelte réduit les
 * `$effect` à rien : un effet qui boucle n'y boucle jamais. Ce fichier ne change que la
 * compilation — pas de DOM, pas de jsdom (le projet n'en dépend pas). Le projet de test
 * `runes` de `vite.config.ts` l'applique aux `*.svelte.test.ts` : la docblock
 * `@vitest-environment` n'accepte qu'un nom de paquet, pas un chemin.
 */
import type { Environment } from 'vitest/runtime';

export default {
	name: 'runes',
	viteEnvironment: 'client',
	setup() {
		return { teardown() {} };
	}
} satisfies Environment;
