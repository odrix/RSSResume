<script lang="ts">
	import ContenuJournee from '#lib/ContenuJournee.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const formatDate = new Intl.DateTimeFormat('fr-FR', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		timeZone: 'UTC'
	});

	const titre = $derived.by(() => {
		const texte = formatDate.format(new Date(`${data.contenu.date}T00:00:00Z`));
		return `Veille du ${texte}`;
	});
</script>

<svelte:head>
	<title>{titre} — RSSResume</title>
</svelte:head>

<p><a href="/resumes/{encodeURIComponent(data.username)}">← {data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`}</a></p>

<h1>{titre}</h1>

{#if data.contenu.ecoute || data.contenu.categories.length}
	<p class="attenue">
		{data.contenu.racontees}/{data.contenu.categories.length} catégorie{data.contenu.categories.length > 1 ? 's' : ''}{#if data.contenu.ecoute} · {data.contenu.ecoute} d'écoute{/if}
	</p>
{/if}

<ContenuJournee contenu={data.contenu} username={data.username} />
