<script lang="ts">
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
</script>

<svelte:head>
	<title>Connexion — RSSResume</title>
</svelte:head>

<h1>Connexion</h1>

{#if form?.message}
	<p class="message erreur" role="alert">{form.message}</p>
{/if}

<form method="POST" class="formulaire carte">
	<label>
		Adresse email
		<input type="email" name="email" autocomplete="email" required value={form?.email ?? ''} />
	</label>
	<label>
		Mot de passe
		<input type="password" name="motDePasse" autocomplete="current-password" required />
	</label>
	<button type="submit">Se connecter</button>
	<p class="attenue">Pas encore de compte ? <a href="/inscription">Créer un compte</a></p>
</form>
