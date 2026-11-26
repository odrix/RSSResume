<!--
	Une section secondaire de la page profil : un bouton résumant l'état actuel, qui ouvre
	une popup d'édition. La popup reste DANS le formulaire parent : les champs d'un
	<dialog> fermé sont quand même soumis, l'enregistrement ne change pas.

	`ouvert` sert au rendu serveur après un refus : le dialog du champ signalé est rendu
	avec l'attribut `open`, pour que l'erreur soit visible sans clic.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		titre,
		resume,
		ouvert = false,
		children
	}: {
		/** Libellé du bouton, ex. « Régime de sécurité ». */
		titre: string;
		/** L'état actuel en quelques mots, ex. « Exploitant », « 3 adresses ». */
		resume: string;
		/** Rendu avec l'attribut `open` quand le serveur a refusé un champ de la section. */
		ouvert?: boolean;
		/** Le contenu d'édition : champs, aides, erreurs, inchangés. */
		children: Snippet;
	} = $props();

	let dialog: HTMLDialogElement | undefined = $state();
</script>

<button type="button" class="secondaire popup-bouton" onclick={() => dialog?.showModal()}>
	<strong>{titre}</strong>
	<span class="aide">{resume}</span>
</button>
<dialog bind:this={dialog} open={ouvert} aria-label={titre} class="popup-dialog">
	<div class="popup-contenu">
		{@render children()}
		<button type="button" class="secondaire" onclick={() => dialog?.close()}>Fermer</button>
	</div>
</dialog>

<style>
	.popup-bouton {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: baseline;
		justify-self: stretch;
		text-align: left;
	}

	.popup-dialog {
		border: 3px solid var(--bord);
		border-radius: var(--rayon);
		box-shadow: var(--ombre);
		background: var(--surface);
		color: var(--texte);
		padding: 1rem 1.25rem;
		max-width: min(42rem, 92vw);
		max-height: 85vh;
		overflow: auto;
	}

	.popup-dialog::backdrop {
		background: rgba(17, 17, 17, 0.55);
	}

	.popup-contenu {
		display: grid;
		gap: 1rem;
	}
</style>
