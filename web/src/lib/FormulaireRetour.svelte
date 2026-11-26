<!--
	Le formulaire du vote « utile / pas utile », le même sur la page du lien de la lettre et
	sur celle des résumés : deux façons de voter qui se remplacent l'une l'autre doivent
	demander la même chose.

	Rien n'est compté avant l'envoi, et la page le dit : ouvrir le lien, ce que fait aussi un
	antivirus de messagerie : ne vote pas.
-->
<script lang="ts">
	import { AVIS, LIBELLES_AVIS, LONGUEUR_MAX_COMMENTAIRE, type Avis } from '#lib/retour.js';

	let {
		avis = null,
		commentaire = '',
		message = null,
		dejaVote = false
	}: {
		/** L'avis pré-coché : celui du lien cliqué, ou le vote déjà donné. */
		avis?: Avis | null;
		/** Le commentaire déjà laissé, ou celui d'un envoi refusé : jamais perdu. */
		commentaire?: string;
		message?: string | null;
		/** Vrai quand un vote existe déjà : l'envoi le remplacera. */
		dejaVote?: boolean;
	} = $props();
</script>

<form method="POST" class="formulaire carte">
	{#if message}<p class="message erreur" role="alert">{message}</p>{/if}
	<fieldset class="bloc" role="radiogroup">
		<legend><strong>Cette journée vous a-t-elle été utile ?</strong></legend>
		{#each AVIS as valeur (valeur)}
			<label class="case">
				<input type="radio" name="avis" value={valeur} checked={avis === valeur} required />
				<span>{LIBELLES_AVIS[valeur]}</span>
			</label>
		{/each}
	</fieldset>
	<label>
		<span>Un commentaire ? <span class="aide">(facultatif, {LONGUEUR_MAX_COMMENTAIRE} caractères au plus)</span></span>
		<textarea name="commentaire" rows="5" maxlength={LONGUEUR_MAX_COMMENTAIRE} value={commentaire}></textarea>
	</label>
	<p class="aide">
		Votre avis n'est compté qu'une fois envoyé{dejaVote ? ', et il remplacera le précédent' : ''}.
	</p>
	<button type="submit">Envoyer mon avis</button>
</form>

<style>
	.bloc {
		display: grid;
		gap: 0.5rem;
		border: 1px solid var(--bord);
		border-radius: var(--rayon);
		padding: 0.75rem 1rem 1rem;
		margin: 0;
	}

	.case {
		display: flex;
		gap: 0.6rem;
		align-items: flex-start;
		font-weight: 400;
	}

	.case input {
		width: auto;
		margin-top: 0.3rem;
	}

	.formulaire p {
		margin: 0;
	}
</style>
