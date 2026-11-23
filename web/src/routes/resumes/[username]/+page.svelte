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

	const urlJournee = (date: string) =>
		`/resumes/${encodeURIComponent(data.username)}/${encodeURIComponent(date)}`;

	/** « lundi 23 novembre à 04:00 », dans le fuseau du passage et non celui du navigateur :
	 * c'est l'heure où le travailleur passe, pas celle où on lit la page. Le début du passage
	 * et non l'arrivée du résumé, que la durée de la tournée repousse d'autant. */
	const prochainPassage = $derived.by(() => {
		if (!data.passage) return null;
		const moment = new Date(data.passage.prochain);
		if (Number.isNaN(moment.getTime())) return null;
		try {
			const jour = new Intl.DateTimeFormat('fr-FR', {
				weekday: 'long',
				day: 'numeric',
				month: 'long',
				timeZone: data.passage.fuseau
			}).format(moment);
			const heure = new Intl.DateTimeFormat('fr-FR', {
				hour: '2-digit',
				minute: '2-digit',
				timeZone: data.passage.fuseau
			}).format(moment);
			return `${jour} à ${heure}`;
		} catch {
			return null; // fuseau inconnu du navigateur : la phrase sans heure
		}
	});
</script>

<svelte:head>
	<title>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`} — RSSResume</title>
</svelte:head>

<header class="titre-page">
	<p class="eyebrow">Lecture · veille quotidienne</p>
	<h1>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`}</h1>
</header>

{#if data.erreur}
	<p class="message erreur" role="alert">{data.erreur}</p>
{:else if !data.journees.length}
	<div class="carte">
		<p class="attenue">
			{#if prochainPassage}
				Aucun résumé pour l'instant. {data.proprietaire
					? 'Votre premier résumé'
					: `Le premier résumé de ${data.username}`} arrivera après le passage du {prochainPassage}.
			{:else}
				Aucun résumé pour l'instant. Le premier arrivera après le prochain passage quotidien.
			{/if}
		</p>
	</div>
{/if}

<ul class="journees">
	{#each data.journees as journee (journee.date)}
		<li class="carte journee">
			<div class="entete-journee">
				<p class="date">{dateLisible(journee.date)}</p>
				<span class="nombre">{journee.audios.length} audio{journee.audios.length > 1 ? 's' : ''}</span>
			</div>
			<a class="bouton lire" href={urlJournee(journee.date)}>Lire la veille</a>
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
	.titre-page {
		margin-bottom: 1.5rem;
	}

	.eyebrow {
		display: inline-block;
		margin: 0 0 1rem;
		padding: 0.35rem 0.65rem;
		background: var(--texte);
		color: var(--accent);
		text-transform: uppercase;
	}

	.journee {
		display: grid;
		gap: 1rem;
	}

	.entete-journee {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		align-items: flex-start;
		border-bottom: 2px solid var(--bord);
	}

	.date {
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		font-size: 1.45rem;
		line-height: 1;
		text-transform: uppercase;
		margin: 0 0 0.75rem;
	}

	.nombre {
		background: var(--accent);
		border: 2px solid var(--bord);
		padding: 0.15rem 0.4rem;
		white-space: nowrap;
		font-size: 0.8rem;
	}

	.lire {
		justify-self: start;
	}

	h1 {
		margin-bottom: 0;
	}
</style>
