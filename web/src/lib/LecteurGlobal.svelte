<!--
	Le mini-lecteur du layout : la journée en cours d'écoute, quand la page visitée ne lui offre
	pas d'emplacement plein. Il ne porte pas l'audio — le `LecteurAudio` le fait, hors markup —
	et ne rend donc rien du tout tant qu'aucune piste n'est lancée : pas de lecteur vide.

	Une réserve de hauteur suit le pied de page, pour que le mini-lecteur, fixé en bas, ne
	recouvre jamais la fin de la page.
-->
<script lang="ts">
	import { lecteurAudio, minutesSecondes } from '#lib/lecteur.svelte.js';

	const lecteur = lecteurAudio();

	const temps = $derived(`${minutesSecondes(lecteur.position)} / ${minutesSecondes(lecteur.duree)}`);
</script>

{#if lecteur.afficherMini && lecteur.piste}
	{@const piste = lecteur.piste}
	<div class="mini-lecteur-reserve" aria-hidden="true"></div>
	<div class="mini-lecteur" role="region" aria-label="Lecteur audio">
		<button
			type="button"
			class="lecture-pause"
			aria-label={lecteur.enLecture ? 'Pause' : 'Lecture'}
			onclick={() => lecteur.basculer()}
		>
			<span aria-hidden="true">{lecteur.enLecture ? '❚❚' : '▶'}</span>
		</button>
		<div class="mini-infos">
			<div class="lecteur-entete">
				<strong>{piste.titre}</strong>
				<span class="temps">{temps}</span>
			</div>
			<progress value={lecteur.position} max={lecteur.duree || 1}>{temps}</progress>
		</div>
		<a class="ouvrir" href={piste.pageJournee}>Ouvrir la journée</a>
		<button type="button" class="fermer" aria-label="Fermer le lecteur" onclick={() => lecteur.fermer()}>×</button>
	</div>
{/if}
