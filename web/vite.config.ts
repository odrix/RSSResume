import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter(),
			// La protection CSRF de SvelteKit est levée ici et réécrite dans `hooks.server.ts`
			// (`src/lib/server/csrf.ts`), à l'identique sauf pour une route : le désabonnement
			// en un clic, que Gmail et Yahoo postent depuis le client mail, sans `Origin`.
			// Retirer cette ligne sans retirer l'exception casserait ce désabonnement ; la
			// garder sans le hook ouvrirait tous les formulaires aux autres sites.
			csrf: { trustedOrigins: ['*'] },
			// Le site ne charge rien d'ailleurs : ni police, ni script, ni image tierce. Les
			// scripts de SvelteKit reçoivent un nonce ; les styles gardent 'unsafe-inline' parce
			// que Vite les injecte en développement et que le risque d'un style injecté est
			// sans commune mesure avec celui d'un script.
			csp: {
				mode: 'auto',
				directives: {
					'default-src': ['self'],
					'script-src': ['self'],
					'style-src': ['self', 'unsafe-inline'],
					'img-src': ['self', 'data:'],
					'media-src': ['self'],
					'connect-src': ['self'],
					'form-action': ['self'],
					'frame-ancestors': ['none'],
					'base-uri': ['self'],
					'object-src': ['none']
				}
			}
		})
	],
	test: {
		expect: { requireAssertions: true },
		environment: 'node',
		// `node:sqlite` s'annonce expérimental à chaque processus ; le serveur fait taire ce
		// même avertissement (script `start`, Dockerfile).
		execArgv: ['--disable-warning=ExperimentalWarning'],
		projects: [
			{
				extends: true,
				test: {
					name: 'serveur',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.test.ts']
				}
			},
			// Les `*.svelte.test.ts` testent des runes : compilés pour le client, avec le runtime
			// client de Svelte (sans quoi `$effect` n'est qu'une coquille vide), toujours sans DOM.
			{
				extends: true,
				resolve: { conditions: ['browser'] },
				test: {
					name: 'runes',
					include: ['src/**/*.svelte.test.ts'],
					environment: './src/lib/environnement-runes.ts',
					server: { deps: { inline: ['svelte'] } }
				}
			}
		]
	}
});
