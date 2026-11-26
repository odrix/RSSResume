<!--
	L'emplacement qu'une page offre à une piste : tant qu'il est monté, le mini-lecteur du
	layout s'efface pour cette piste, et la page la pilote en pleine largeur. Quitter la page
	retire l'emplacement sans toucher à l'audio, qui continue dans le mini-lecteur.

	Hors de la piste en cours, c'est un lien vers le MP3 : sans JavaScript, il s'ouvre dans le
	lecteur du navigateur ; avec, il lance le lecteur du site à la place.
-->
<script lang="ts">
	import { lecteurAudio, minutesSecondes, type PisteAudio } from '#lib/lecteur.svelte.js';

	let { piste }: { piste: PisteAudio } = $props();

	const lecteur = lecteurAudio();

	$effect(() => lecteur.ancrer(piste.cle));

	const courante = $derived(lecteur.piste?.cle === piste.cle);
	const temps = $derived(`${minutesSecondes(lecteur.position)} / ${minutesSecondes(lecteur.duree)}`);

	function ecouter(evenement: MouseEvent): void {
		evenement.preventDefault();
		lecteur.lancer(piste);
	}

	function chercher(evenement: Event): void {
		lecteur.chercher(Number((evenement.currentTarget as HTMLInputElement).value));
	}
</script>

{#if courante}
	<div class="lecteur-plein">
		<button
			type="button"
			class="lecture-pause"
			aria-label={lecteur.enLecture ? 'Pause' : 'Lecture'}
			onclick={() => lecteur.basculer()}
		>
			<span aria-hidden="true">{lecteur.enLecture ? '❚❚' : '▶'}</span>
		</button>
		<input
			type="range"
			min="0"
			max={lecteur.duree || 0}
			step="1"
			value={lecteur.position}
			oninput={chercher}
			aria-label="Position dans l'écoute"
		/>
		<span class="temps">{temps}</span>
	</div>
{:else}
	<a class="bouton ecouter" href={piste.url} onclick={ecouter}>
		<span aria-hidden="true">▶</span> Écouter
	</a>
{/if}

<style>
	.lecteur-plein {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: 0.75rem;
	}

	.lecteur-plein input {
		padding: 0;
		border: 0;
		background: none;
		accent-color: var(--texte);
	}

	.lecture-pause {
		padding: 0.5rem 0.75rem;
		box-shadow: none;
	}

	.temps {
		font-variant-numeric: tabular-nums;
	}

	.ecouter {
		display: inline-block;
		justify-self: start;
	}
</style>
