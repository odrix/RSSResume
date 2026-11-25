<script lang="ts">
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
</script>

<svelte:head>
	<title>Mot de passe oublié — RSSResume</title>
</svelte:head>

<h1>Mot de passe oublié</h1>

{#if form && 'envoye' in form}
	<p class="message succes" role="status">{form.envoye}</p>
{:else if form && 'message' in form}
	<p class="message erreur" role="alert">{form.message}</p>
{/if}

<form method="POST" class="formulaire carte">
	<label>
		Adresse email du compte
		<input type="email" name="email" autocomplete="email" required value={form?.email ?? ''} />
	</label>
	<button type="submit">Recevoir un lien</button>
	<p class="attenue"><a href="/connexion">Retour à la connexion</a></p>
</form>
