<script lang="ts">
	import '#lib/style.css';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<svelte:head>
	<title>RSSResume</title>
</svelte:head>

<header class="entete">
	<nav aria-label="Navigation principale">
		<a class="marque" href="/">RSSResume</a>
		{#if data.utilisateur}
			<a href="/resumes">Mes résumés</a>
			<a href="/profil">Mon profil</a>
			{#if data.utilisateur.admin}
				<a href="/admin">Administration</a>
			{/if}
			<form method="POST" action="/deconnexion" class="deconnexion">
				<span class="qui">{data.utilisateur.username}</span>
				<button type="submit" class="lien">Se déconnecter</button>
			</form>
		{:else}
			<a href="/connexion">Se connecter</a>
			<a href="/inscription">Créer un compte</a>
		{/if}
	</nav>
</header>

<main>
	{@render children()}
</main>
