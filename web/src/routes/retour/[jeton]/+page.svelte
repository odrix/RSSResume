<script lang="ts">
	import FormulaireRetour from '#lib/FormulaireRetour.svelte';
	import { LIBELLES_AVIS } from '#lib/retour.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const formatDate = new Intl.DateTimeFormat('fr-FR', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		timeZone: 'UTC'
	});
	const journee = (jour: string) => formatDate.format(new Date(`${jour}T00:00:00Z`));
</script>

<svelte:head>
	<title>Votre avis, RSSResume</title>
</svelte:head>

<h1>Votre avis</h1>

{#if form?.vote?.retour}
	<p class="message succes" role="status">
		Merci : votre avis « {LIBELLES_AVIS[form.vote.retour.avis]} » sur la veille du
		{journee(form.vote.jour)} est enregistré.
	</p>
	<p>
		Vous pouvez le changer en rouvrant le lien de la lettre : le dernier avis envoyé remplace
		le précédent.
	</p>
{:else if data.invalide}
	<p class="message erreur" role="alert">{data.invalide}</p>
	<p><a href="/resumes">Voir mes résumés</a></p>
{:else if data.lecture}
	<p>
		Veille du <strong>{journee(data.lecture.jour)}</strong>, profil « {data.lecture.username} ».
	</p>
	<FormulaireRetour
		avis={form?.message ? (form.avis ?? null) : data.avis}
		commentaire={form?.message ? (form.commentaire ?? '') : (data.lecture.retour?.commentaire ?? '')}
		message={form?.message ?? null}
		dejaVote={data.lecture.retour !== null}
	/>
{/if}
