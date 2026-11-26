<script lang="ts">
	import ContenuJournee from '#lib/ContenuJournee.svelte';
	import FormulaireRetour from '#lib/FormulaireRetour.svelte';
	import { LIBELLES_AVIS } from '#lib/retour.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	/** Le vote à montrer : celui qu'on vient d'envoyer, sinon celui déjà donné. */
	const retour = $derived(form?.vote ?? data.retour);

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
	<title>{titre}, RSSResume</title>
</svelte:head>

<p class="retour"><a class="bouton bouton-secondaire" href="/resumes/{encodeURIComponent(data.username)}">← {data.proprietaire ? 'Mes résumés' : `Résumés de ${data.username}`}</a></p>

<header class="titre-page">
	<p class="eyebrow">Lecture · veille textuelle</p>
	<h1>{titre}</h1>
</header>

{#if data.contenu.ecoute || data.contenu.categories.length}
	<p class="bilan">
		<span>{data.contenu.racontees}/{data.contenu.categories.length} catégorie{data.contenu.categories.length > 1 ? 's' : ''}</span>
		{#if data.contenu.ecoute}<span>{data.contenu.ecoute} d'écoute</span>{/if}
	</p>
{/if}

<ContenuJournee contenu={data.contenu} username={data.username} />

{#if data.proprietaire}
	<section class="avis">
		<h2>Votre avis sur cette journée</h2>
		{#if form?.vote}
			<p class="message succes" role="status">
				Merci : votre avis « {LIBELLES_AVIS[form.vote.avis]} » est enregistré.
			</p>
		{/if}
		<FormulaireRetour
			avis={retour?.avis ?? null}
			commentaire={form?.message ? (form.commentaire ?? '') : (retour?.commentaire ?? '')}
			message={form?.message ?? null}
			dejaVote={retour !== null}
		/>
	</section>
{/if}

<style>
	.retour {
		margin: 0 0 1.5rem;
	}

	.eyebrow {
		display: inline-block;
		margin: 0 0 1rem;
		padding: 0.35rem 0.65rem;
		background: var(--texte);
		color: var(--accent);
		text-transform: uppercase;
	}

	.titre-page {
		margin-bottom: 1.25rem;
	}

	.bilan {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 0 0 1.5rem;
	}

	.bilan span {
		border: 2px solid var(--bord);
		background: var(--accent);
		padding: 0.25rem 0.55rem;
	}

	.avis {
		margin-top: 2.5rem;
	}
</style>
