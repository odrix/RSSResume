<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Recevoir un lien de connexion — RSSResume</title>
</svelte:head>

<h1>Recevoir un lien de connexion</h1>

{#if data.dejaConnecte}
	<p class="message info" role="status">Vous êtes déjà connecté.</p>
{:else if form?.envoye}
	<p class="message succes" role="status">
		Si un compte existe avec cette adresse, vous allez recevoir un email avec un lien de connexion.
	</p>
{:else if form?.message}
	<p class="message erreur" role="alert">{form.message}</p>
{/if}

<p>
	Saisissez votre adresse email pour recevoir un lien vous permettant de vous connecter.
	Ce lien est valable 15 minutes et ne peut être utilisé qu'une seule fois.
</p>

<form method="POST" class="formulaire carte">
	<label>
		Adresse email
		<input type="email" name="email" autocomplete="email" required value={form?.email ?? ''} />
	</label>
	<button type="submit">Recevoir un lien</button>
</form>

<p class="attenue">
	<a href="/connexion">Se connecter avec un mot de passe</a> ·
	<a href="/inscription">Créer un compte</a>
</p>
