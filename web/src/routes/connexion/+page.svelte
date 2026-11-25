<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Connexion — RSSResume</title>
</svelte:head>

<h1>Connexion</h1>

{#if data.confirme && !form}
	<p class="message succes" role="status">Votre adresse est confirmée. Vous pouvez vous connecter.</p>
{/if}
{#if data.reinitialise && !form}
	<p class="message succes" role="status">Votre mot de passe est changé. Connectez-vous avec le nouveau.</p>
{/if}
{#if form?.message}
	<p class="message erreur" role="alert">
		{form.message}
		{#if form && 'nonConfirme' in form}
			<a href="/renvoyer-lien?email={encodeURIComponent(form.email)}">Recevoir un nouveau lien</a>
		{/if}
	</p>
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
	<p class="attenue"><a href="/mot-de-passe-oublie">Mot de passe oublié ?</a></p>
	<button type="submit">Se connecter</button>
	<p class="attenue">
		Pas encore de compte ? <a href="/inscription">Créer un compte</a> ·
		<a href="/renvoyer-lien">Renvoyer le lien de confirmation</a>
	</p>
	<p class="attenue">
		<a href="/demander-lien">Se connecter avec un lien magique</a>
	</p>
</form>
