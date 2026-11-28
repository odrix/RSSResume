<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>RSSResume — votre veille, résumée et lue à voix haute</title>
</svelte:head>

<section class="accueil">
	<p class="eyebrow">Votre veille professionnelle</p>
	<h1>Votre veille, résumée et lue à voix haute</h1>
	<!-- Avant le bloc exemple dans le DOM : la mention reste visible sans défiler, même sur mobile. -->
	<p class="beta">Service en <strong>bêta</strong> — vos retours décident de la suite.</p>

	<div class="carte presentation">
		<p class="accroche">
			RSSResume lit les articles de la veille, garde ceux qui comptent pour vous,
			les résume et en fait un épisode audio envoyé par email.
		</p>
		<p>
			Ce que « compter pour vous » veut dire, c'est votre <strong>profil</strong> qui le décide :
			votre métier, vos axes de veille et les composants que vous exploitez.
		</p>
	</div>

	<div class="carte exemple">
		<h2>Un exemple de ce que vous recevrez</h2>
		<p>
			Chaque matin, un email avec le résumé de la veille, catégorie par catégorie, et un
			épisode audio à écouter. Voici un extrait de lettre et un court extrait sonore,
			tirés d'une journée d'exemple :
		</p>
		<blockquote class="extrait">
			{#each data.extraitLettre.trim().split('\n\n') as paragraphe}
				<p>{paragraphe}</p>
			{/each}
		</blockquote>
		<div class="audio">
			<audio controls src={data.audioExemple}>Votre navigateur ne sait pas lire l'audio.</audio>
		</div>
	</div>

	<div class="carte explication">
		<h2>Ce que vous recevez, et quand</h2>
		<p>
			Le digest de la veille arrive <strong>le lendemain matin par email</strong>, avec le texte
			des résumés et les épisodes audio en pièces jointes : rien à ouvrir avant, rien à
			lancer soi-même.
		</p>
		<p>
			Le service est en <strong>bêta</strong> : il évolue, et ce sont
			<strong>vos retours qui décident de la suite</strong> — dites-nous ce qui vous a été utile.
		</p>
		<div class="actions">
			<a class="bouton" href="/inscription">Créer un compte</a>
			<a class="bouton bouton-secondaire" href="/connexion">Se connecter</a>
		</div>
	</div>
</section>

<style>
	.accueil {
		padding-top: 1.5rem;
	}

	.eyebrow {
		display: inline-block;
		margin: 0 0 1.25rem;
		padding: 0.35rem 0.65rem;
		background: var(--texte);
		color: var(--accent);
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.beta {
		display: inline-block;
		margin: -0.5rem 0 1.25rem;
		padding: 0.35rem 0.65rem;
		border: 3px solid var(--bord);
		border-radius: var(--rayon);
		background: var(--surface-jaune);
		font-weight: 700;
	}

	.presentation {
		max-width: 48rem;
	}

	.accroche {
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		font-size: clamp(1.35rem, 3vw, 2.1rem);
		line-height: 1.12;
		text-transform: uppercase;
		margin-top: 0;
	}

	.exemple {
		max-width: 48rem;
	}

	.extrait {
		margin: 0 0 1rem;
		padding: 0.75rem 1rem;
		border-left: 4px solid var(--bord);
		background: var(--surface-jaune);
	}

	.extrait p {
		margin: 0 0 0.5rem;
	}

	.extrait p:last-child {
		margin-bottom: 0;
	}

	.exemple h2,
	.explication h2 {
		margin-top: 0;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-top: 1.5rem;
	}

	.bouton-secondaire {
		background: var(--surface);
		color: var(--texte);
	}

	@media (max-width: 520px) {
		.accueil {
			padding-top: 0.25rem;
		}

		.actions {
			display: grid;
		}

		.bouton {
			width: 100%;
			text-align: center;
		}
	}
</style>
