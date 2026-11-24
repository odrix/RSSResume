<script lang="ts">
	import '#lib/style.css';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
	let stylePage = $state<'brutal' | 'minimaliste'>('brutal');

	function appliquerStyle(style: 'brutal' | 'minimaliste'): void {
		stylePage = style;
		document.documentElement.dataset.stylePage = style;
		localStorage.setItem('rssresume-style-page', style);
	}

	function changerStyle(evenement: Event): void {
		const select = evenement.currentTarget as HTMLSelectElement;
		appliquerStyle(select.value === 'minimaliste' ? 'minimaliste' : 'brutal');
	}

	onMount(() => {
		if (!data.utilisateur?.admin) {
			appliquerStyle('brutal');
			return;
		}
		const enregistre = localStorage.getItem('rssresume-style-page');
		if (enregistre === 'minimaliste' || enregistre === 'maquette') {
			appliquerStyle('minimaliste');
			return;
		}
		appliquerStyle('brutal');
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
			{#if data.utilisateur.admin}
				<label class="choix-style">
					<span>Style de page</span>
					<select value={stylePage} onchange={changerStyle}>
						<option value="brutal">Brutal</option>
						<option value="minimaliste">Minimaliste</option>
					</select>
				</label>
			{/if}
			<form method="POST" action="/deconnexion" class="deconnexion">
				<span class="qui">{data.utilisateur.username}</span>
				<button type="submit" class="lien">Se déconnecter</button>
			</form>
			{#if data.utilisateur.admin}
				<a class="administration" href="/admin">Administration</a>
			{/if}
		{:else}
			<a href="/connexion">Se connecter</a>
			<a href="/inscription">Créer un compte</a>
		{/if}
	</nav>
</header>

<main>
	{@render children()}
</main>
