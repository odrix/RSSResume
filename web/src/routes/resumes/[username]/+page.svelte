<script lang="ts">
	import { dateLisible } from '#lib/journee.js';
	import { PisteAudio, lecteurAudio } from '#lib/lecteur.svelte.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const lecteur = lecteurAudio();
	let durees = $state<Record<string, string>>({});

	function datePieces(iso: string): { jourEtNumero: string; moisAnnee: string } {
		const texte = dateLisible(iso);
		const parties = texte.split(' ');
		if (parties.length < 4) return { jourEtNumero: texte, moisAnnee: '' };
		return {
			jourEtNumero: parties.slice(0, 2).join(' '),
			moisAnnee: parties.slice(2).join(' ')
		};
	}

	function cleAudio(date: string, nom: string): string {
		return `${date}/${nom}`;
	}

	function dureeLisible(secondes: number): string {
		if (!Number.isFinite(secondes)) return '';
		const minutes = Math.max(1, Math.round(secondes / 60));
		return `${minutes} min`;
	}

	function pluriel(nombre: number, singulier: string, plurielTexte: string): string {
		return `${nombre} ${nombre > 1 ? plurielTexte : singulier}`;
	}

	function lireMeta(date: string, nom: string, evenements: Event): void {
		const element = evenements.currentTarget as HTMLAudioElement;
		const duree = dureeLisible(element.duration);
		if (duree) durees = { ...durees, [cleAudio(date, nom)]: duree };
	}

	/** Ce que joue la carte : son premier fichier n'est la journée entière que s'il en est le
	 * montage, comme sur la page de la journée. */
	function pisteDeCarte(date: string, nom: string): PisteAudio {
		const indicateurs = data.indicateursJournees?.[date];
		return PisteAudio.pourFichier(
			data.username,
			date,
			nom,
			indicateurs?.montage ?? null,
			indicateurs?.categoriesAudio?.[nom] ?? null
		);
	}

	/** La carte ne porte pas de lecteur : elle lance celui du layout, qui continue d'une page à
	 * l'autre, ou le met en pause quand c'est déjà sa piste qui joue. */
	function lire(piste: PisteAudio): void {
		if (lecteur.piste?.cle === piste.cle) lecteur.basculer();
		else lecteur.lancer(piste);
	}

	const enLecture = (piste: PisteAudio) => lecteur.piste?.cle === piste.cle && lecteur.enLecture;

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
		{@const indicateurs = data.indicateursJournees?.[journee.date]}
		{@const date = datePieces(journee.date)}
		<li class="carte journee">
			{#if journee.audios.length}
				{@const audio = journee.audios[0]}
				{@const piste = pisteDeCarte(journee.date, audio.nom)}
				<audio class="meta-audio" preload="metadata" src={urlAudio(journee.date, audio.nom)} onloadedmetadata={(evenement) => lireMeta(journee.date, audio.nom, evenement)}></audio>
				<div class="titre-carte">
					<h2>
						<span class="date-ligne">
							<span class="date-principale">{date.jourEtNumero}</span>
						</span>
						{#if date.moisAnnee}
							<span class="date-secondaire">{date.moisAnnee}</span>
						{/if}
					</h2>
					<span class="duree-principale">{(indicateurs?.ecoute ?? durees[cleAudio(journee.date, audio.nom)] ?? '...').toUpperCase()}</span>
				</div>
				<ul class="stats-journee">
					<li>{pluriel(indicateurs?.categories ?? 0, 'catégorie', 'catégories')}</li>
					<li>{pluriel(indicateurs?.articles ?? 0, 'article', 'articles')}</li>
				</ul>
				<div class="actions">
					<button type="button" class="lecture" onclick={() => lire(piste)}>
						<span class="icone-lecture" aria-hidden="true">{enLecture(piste) ? '❚❚' : '▶'}</span>
						<span class="texte-lecture">{enLecture(piste) ? 'Pause' : 'Lecture'}</span>
					</button>
					<a class="resume-secondaire" href={urlJournee(journee.date)}>Lire le résumé</a>
				</div>
			{:else}
				<div class="titre-carte">
					<h2>
						<span class="date-ligne">
							<span class="date-principale">{date.jourEtNumero}</span>
							<span class="duree-principale">{(indicateurs?.ecoute ?? '...').toUpperCase()}</span>
						</span>
						{#if date.moisAnnee}
							<span class="date-secondaire">{date.moisAnnee}</span>
						{/if}
					</h2>
				</div>
				<ul class="stats-journee">
					<li>{pluriel(indicateurs?.categories ?? 0, 'catégorie', 'catégories')}</li>
					<li>{pluriel(indicateurs?.articles ?? 0, 'article', 'articles')}</li>
				</ul>
				<div class="actions">
					<a class="resume-secondaire seul" href={urlJournee(journee.date)}>Lire le résumé</a>
				</div>
			{/if}
		</li>
	{/each}
</ul>

<style>
	:global(main) {
		max-width: 76rem;
	}

	.journees {
		display: flex;
		flex-wrap: wrap;
		direction: row;
	}

	.journee {
		min-height: 18.5rem;
		padding: 1rem;
		margin-bottom: 0;
		display: flex;
		flex-direction: column;
		justify-content: flex-start;
		overflow: hidden;
		width: 28%;
	}

	.titre-carte {
		display: flex;
		justify-content: space-between;
		margin-bottom: 0.95rem;
	}

	.stats-journee {
		margin: 0 0 1rem;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.2rem;
		font-size: 1.1rem;
		font-weight: 600;
		line-height: 1.2;
		font-family: Arial, Helvetica, sans-serif;
		text-transform: uppercase;
	}

	.stats-journee li::before {
		content: '• ';
		font-weight: 700;
	}

	.duree-principale {
		background: var(--texte);
  min-height: 1.25rem;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  align-items: center;
  padding: .25rem .75rem;
  font-family: Impact,Arial Black,Arial,sans-serif;
  font-size: 1rem;
  line-height: 1;
  display: inline-flex;
  height: 70%;
	}

	.journee h2 {
		display: grid;
		gap: 0.1rem;
		font-size: clamp(1.25rem, 2.2vw, 2.2rem);
		line-height: 0.98;
		margin: 0;
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	.date-principale {
		display: inline-block;
		font-size: 1.1em;
	}

	.date-ligne {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		width: 100%;

	}

	.date-secondaire {
		display: block;
		font-size: 0.7em;
		line-height: 1;
	}

	.actions {
		display: grid;
		gap: 0.55rem;
		margin-top: auto;
	}

	.lecture {
		width: 100%;
		display: inline-flex;
		justify-content: center;
		align-items: center;
		gap: 0.55rem;
		min-height: 3rem;
		font-size: 1.05rem;
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		text-transform: uppercase;
	}

	.icone-lecture {
		display: inline-grid;
		place-items: center;
		width: 1.8rem;
		height: 1.8rem;
		border: 2px solid var(--texte);
		border-radius: 50%;
		font-size: 0.75rem;
		padding-left: 0.12rem;
	}

	.resume-secondaire {
		display: inline-flex;
		justify-content: center;
		align-items: center;
		min-height: 2.45rem;
		border: 3px solid var(--bord);
		background: var(--surface);
		box-shadow: 5px 5px 0 var(--bord);
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		font-size: 1rem;
		text-decoration: none;
		text-transform: uppercase;
	}

	.resume-secondaire.seul {
		margin-top: auto;
	}

	.meta-audio {
		display: none;
	}

	@media (max-width: 1100px) {
		.journees {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.journee {
			min-height: 16.5rem;
		}
	}

	@media (max-width: 1500px) {
		.journees {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 520px) {
		.journees {
			grid-template-columns: 1fr;
		}

		.journee {
			min-height: 15rem;
		}

		.lecture,
		.resume-secondaire {
			border-width: 3px;
			box-shadow: 4px 4px 0 var(--bord);
		}

		.journee h2 {
			font-size: clamp(1.2rem, 8vw, 1.85rem);
		}

		.stats-journee {
			font-size: 0.95rem;
		}
	}
</style>
