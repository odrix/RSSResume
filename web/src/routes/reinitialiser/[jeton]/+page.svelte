<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Nouveau mot de passe — RSSResume</title>
</svelte:head>

<h1>Choisir un nouveau mot de passe</h1>

{#if data.invalide || (form && !form.champ)}
	<p class="message erreur" role="alert">{form?.message ?? data.invalide}</p>
	<p><a href="/mot-de-passe-oublie">Demander un nouveau lien</a></p>
{:else}
	<form method="POST" class="formulaire carte">
		<p>Compte <strong>{data.username}</strong>. Toutes ses sessions ouvertes seront fermées.</p>
		<label>
			Nouveau mot de passe
			<span class="aide">Au moins 12 caractères. Une phrase fait très bien l'affaire.</span>
			<input
				type="password"
				name="motDePasse"
				autocomplete="new-password"
				minlength="12"
				required
				aria-invalid={form?.champ === 'motDePasse' ? 'true' : undefined}
			/>
			{#if form?.champ === 'motDePasse'}<span class="erreur-champ">{form.message}</span>{/if}
		</label>
		<button type="submit">Enregistrer le mot de passe</button>
	</form>
{/if}
