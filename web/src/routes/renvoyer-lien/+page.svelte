<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Renvoyer le lien, RSSResume</title>
</svelte:head>

<h1>Renvoyer le lien de confirmation</h1>

{#if form && 'envoye' in form}
	<p class="message succes" role="status">{form.envoye}</p>
{:else if form && 'message' in form}
	<p class="message erreur" role="alert">{form.message}</p>
{/if}

<form method="POST" class="formulaire carte">
	<label>
		Adresse email du compte
		<input type="email" name="email" autocomplete="email" required value={form?.email ?? data.email} />
	</label>
	<button type="submit">Envoyer un nouveau lien</button>
	<p class="attenue"><a href="/connexion">Retour à la connexion</a></p>
</form>
