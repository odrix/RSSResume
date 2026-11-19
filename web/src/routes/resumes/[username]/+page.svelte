<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const formatDate = new Intl.DateTimeFormat('fr-FR', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		timeZone: 'UTC'
	});

	function dateLisible(iso: string): string {
		const texte = formatDate.format(new Date(`${iso}T00:00:00Z`));
		return texte.charAt(0).toUpperCase() + texte.slice(1);
	}

	function taille(octets: number): string {
		return octets >= 1_048_576
			? `${(octets / 1_048_576).toFixed(1).replace('.', ',')} Mo`
			: `${Math.max(1, Math.round(octets / 1024))} Ko`;
	}

	/** `journee.mp3` → « journée », `cyber.mp3` → « cyber » : le nom suffit à distinguer. */
	function libelle(nom: string): string {
		const base = nom.replace(/\.mp3$/i, '').replace(/[-_]+/g, ' ');
		return base === 'journee' ? 'Journée' : base.charAt(0).toUpperCase() + base.slice(1);
	}

	const urlAudio = (date: string, nom: string) =>
		`/audio/${encodeURIComponent(data.username)}/${encodeURIComponent(date)}/${encodeURIComponent(nom)}`;
</script>

<svelte:head>
	<title>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`} — RSSResume</title>
</svelte:head>

<h1>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`}</h1>

{#if data.erreur}
	<p class="message erreur" role="alert">{data.erreur}</p>
{:else if !data.journees.length}
	<p class="attenue">
		Aucun résumé pour l'instant. Le premier arrivera après le prochain passage quotidien.
	</p>
{/if}

<ul class="journees">
	{#each data.journees as journee (journee.date)}
		<li class="carte">
			<h2>{dateLisible(journee.date)}</h2>
			{#each journee.audios as audio (audio.nom)}
				<div class="audio">
					<span>{libelle(audio.nom)} <span class="attenue">· {taille(audio.taille)}</span></span>
					<audio controls preload="none" src={urlAudio(journee.date, audio.nom)}></audio>
				</div>
			{:else}
				<p class="attenue">Pas d'audio ce jour-là.</p>
			{/each}
		</li>
	{/each}
</ul>

<style>
	h2 {
		margin-top: 0;
	}
</style>
