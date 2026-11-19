<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Confirmer l'adresse — RSSResume</title>
</svelte:head>

<h1>Confirmer l'adresse</h1>

{#if form && 'confirme' in form}
	<p class="message succes" role="status">{form.confirme}</p>
{:else if form && 'message' in form}
	<p class="message erreur" role="alert">{form.message}</p>
{:else if data.invalide}
	<p class="message erreur" role="alert">{data.invalide}</p>
	<p><a href="/renvoyer-lien">Demander un nouveau lien</a></p>
{:else}
	<form method="POST" class="formulaire carte">
		<p>
			{#if data.objet === 'inscription'}
				Confirmez que <strong>{data.email}</strong> est bien votre adresse pour activer votre compte.
			{:else}
				Confirmez que <strong>{data.email}</strong> accepte de recevoir le résumé quotidien RSSResume.
			{/if}
		</p>
		<button type="submit">Confirmer</button>
	</form>
{/if}
