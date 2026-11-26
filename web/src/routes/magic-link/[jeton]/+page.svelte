<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Connexion par lien, RSSResume</title>
</svelte:head>

{#if data.invalide}
	<h1>Lien invalide</h1>
	<p class="message erreur" role="alert">{data.invalide}</p>
	<p><a href="/demander-lien">Demander un nouveau lien</a></p>
{:else if form?.message}
	<h1>Erreur</h1>
	<p class="message erreur" role="alert">{form.message}</p>
	<p><a href="/demander-lien">Demander un nouveau lien</a></p>
{:else}
	<h1>Connectez-vous avec ce lien</h1>
	<p>
	Un lien de connexion a été envoyé à <strong>{data.email}</strong>.
	Ce lien est valable 15 minutes et à usage unique.
	</p>
	<p>Cliquez sur le bouton ci-dessous pour vous connecter.</p>

	<form method="POST" class="formulaire carte">
		<button type="submit" class="bouton-primaire">Se connecter</button>
	</form>
	
	<p class="attenue">
		Ce lien ne fonctionne pas ? <a href="/demander-lien">Demander un nouveau lien</a>
	</p>
{/if}
