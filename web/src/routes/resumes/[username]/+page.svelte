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

	let lecteur: HTMLAudioElement;
	let sourceLecture = $state('');
	let titreLecture = $state('');
	let durees = $state<Record<string, string>>({});

	function dateLisible(iso: string): string {
		const texte = formatDate.format(new Date(`${iso}T00:00:00Z`));
		return texte.charAt(0).toUpperCase() + texte.slice(1);
	}

	function cleAudio(date: string, nom: string): string {
		return `${date}/${nom}`;
	}

	function dureeLisible(secondes: number): string {
		if (!Number.isFinite(secondes)) return '';
		const minutes = Math.floor(secondes / 60);
		const reste = Math.round(secondes % 60);
		return `${minutes}:${reste.toString().padStart(2, '0')}`;
	}

	function lireMeta(date: string, nom: string, evenements: Event): void {
		const element = evenements.currentTarget as HTMLAudioElement;
		const duree = dureeLisible(element.duration);
		if (duree) durees = { ...durees, [cleAudio(date, nom)]: duree };
	}

	async function lire(date: string, nom: string): Promise<void> {
		sourceLecture = urlAudio(date, nom);
		titreLecture = dateLisible(date);
		await new Promise<void>((resolve) => queueMicrotask(resolve));
		lecteur?.play();
	}

	const urlAudio = (date: string, nom: string) =>
		`/audio/${encodeURIComponent(data.username)}/${encodeURIComponent(date)}/${encodeURIComponent(nom)}`;

	const urlJournee = (date: string) =>
		`/resumes/${encodeURIComponent(data.username)}/${encodeURIComponent(date)}`;

	const prochainPassage = $derived.by(() => {
		if (!data.passage) return null;
		const moment = new Date(data.passage.prochain);
		if (Number.isNaN(moment.getTime())) return null;
		try {
			const jour = new Intl.DateTimeFormat('fr-FR', {
				weekday: 'long', day: 'numeric', month: 'long', timeZone: data.passage.fuseau
			}).format(moment);
			const heure = new Intl.DateTimeFormat('fr-FR', {
				hour: '2-digit', minute: '2-digit', timeZone: data.passage.fuseau
			}).format(moment);
			return `${jour} à ${heure}`;
		} catch {
			return null;
		}
	});
</script>

<svelte:head>
	<title>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`} — RSSResume</title>
</svelte:head>

<h1>{data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`}</h1>

{#if data.erreur}
	<p class="message erreur" role="alert">{data.erreur}</p>
{:else if !data.journees.length}
	<p class="attenue">
		{#if prochainPassage}
			Aucun résumé pour l'instant. {data.proprietaire
				? 'Votre premier résumé'
				: `Le premier résumé de ${data.username}`} arrivera après le passage du {prochainPassage}.
		{:else}
			Aucun résumé pour l'instant. Le premier arrivera après le prochain passage quotidien.
		{/if}
	</p>
{/if}

<ul class="journees">
	{#each data.journees as journee (journee.date)}
		<li class="carte journee">
			<h2>{dateLisible(journee.date)}</h2>
			<div class="actions">
				<a class="bouton lire" href={urlJournee(journee.date)}>Lire la veille</a>
				{#each journee.audios as audio (audio.nom)}
					<audio class="meta-audio" preload="metadata" src={urlAudio(journee.date, audio.nom)} onloadedmetadata={(evenement) => lireMeta(journee.date, audio.nom, evenement)}></audio>
					<button type="button" class="lecture" onclick={() => lire(journee.date, audio.nom)}>
						<span aria-hidden="true">▶</span>
						Lecture
						{#if durees[cleAudio(journee.date, audio.nom)]}
							<span class="duree">· {durees[cleAudio(journee.date, audio.nom)]}</span>
						{/if}
					</button>
				{:else}
					<span class="attenue">Pas d'audio ce jour-là.</span>
				{/each}
			</div>
		</li>
	{/each}
</ul>

{#if sourceLecture}
	<div class="lecteur-large">
		<div class="lecteur-entete">
			<strong>{titreLecture}</strong>
			<button type="button" class="fermer" aria-label="Fermer le lecteur" onclick={() => { sourceLecture = ''; titreLecture = ''; }}>×</button>
		</div>
		<audio bind:this={lecteur} controls autoplay src={sourceLecture}></audio>
	</div>
{/if}

<style>
	.journees {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
	}

	.journee {
		padding: 0.9rem;
		margin-bottom: 0;
	}

	.journee h2 {
		font-size: 1.15rem;
		margin: 0 0 0.75rem;
	}

	.actions {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		flex-wrap: wrap;
	}

	.lecture {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
	}

	.duree {
		font-variant-numeric: tabular-nums;
	}

	.meta-audio {
		display: none;
	}

	.lecteur-large {
		position: fixed;
		left: 15.5rem;
		right: 0;
		bottom: 0;
		z-index: 30;
		background: var(--surface-jaune);
		border-top: 4px solid var(--bord);
		padding: 0.65rem 1rem 0.8rem;
	}

	.lecteur-entete {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.35rem;
	}

	.fermer {
		padding: 0.15rem 0.55rem;
		box-shadow: none;
	}

	.lecteur-large audio {
		display: block;
		width: 100%;
	}

	@media (max-width: 900px) {
		.journees {
			grid-template-columns: 1fr;
		}

		.lecteur-large {
			left: 0;
		}
	}
</style>
