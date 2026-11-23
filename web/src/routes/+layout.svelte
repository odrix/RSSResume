<script lang="ts">
	import '#lib/style.css';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
	let stylePage = $state<'actuel' | 'maquette'>('actuel');

	function appliquerStyle(style: 'actuel' | 'maquette'): void {
		stylePage = style;
		document.documentElement.dataset.stylePage = style;
		localStorage.setItem('rssresume-style-page', style);
	}

	function changerStyle(evenement: Event): void {
		const select = evenement.currentTarget as HTMLSelectElement;
		appliquerStyle(select.value === 'maquette' ? 'maquette' : 'actuel');
	}

	onMount(() => {
		const enregistre = localStorage.getItem('rssresume-style-page');
		appliquerStyle(enregistre === 'maquette' ? 'maquette' : 'actuel');
	});
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
			<label class="choix-style">
				<span>Style de page</span>
				<select value={stylePage} onchange={changerStyle}>
					<option value="actuel">Actuel</option>
					<option value="maquette">Maquette</option>
				</select>
			</label>
			<form method="POST" action="/deconnexion" class="deconnexion">
				<span class="qui">{data.utilisateur.username}</span>
				<button type="submit" class="lien">Se déconnecter</button>
			</form>
			{#if data.utilisateur.admin}
				<a class="administration" href="/admin">Administration</a>
			{/if}
		{:else}
			<label class="choix-style">
				<span>Style de page</span>
				<select value={stylePage} onchange={changerStyle}>
					<option value="actuel">Actuel</option>
					<option value="maquette">Maquette</option>
				</select>
			</label>
			<a href="/connexion">Se connecter</a>
			<a href="/inscription">Créer un compte</a>
		{/if}
	</nav>
</header>

<main>
	{@render children()}
</main>
