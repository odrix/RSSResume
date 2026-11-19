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
		include: ['src/**/*.{test,spec}.{js,ts}']
	}
});
