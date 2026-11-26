<!--
	Ce qu'une journée raconte : l'audio, puis par catégorie le résumé et ses articles.

	Tout passe par des expressions `{…}`, que Svelte échappe : le résumé vient du modèle, les
	titres et les sources des flux, et aucun d'eux n'est fiable. Jamais de bloc `@html`. Les liens ne
	deviennent des `href` qu'après `urlSure`, l'échappement ne protégeant pas d'un `javascript:`.
-->
<script lang="ts">
	import LecteurPlein from '#lib/LecteurPlein.svelte';
	import { PisteAudio } from '#lib/lecteur.svelte.js';
	import { paragraphes, urlSure, type ContenuJournee, type LienArticle } from '#lib/journee.js';

	let { contenu, username }: { contenu: ContenuJournee; username: string } = $props();

	/** La même piste que la carte de la liste, pour qu'une écoute lancée là-bas se reprenne ici. */
	const montage = $derived(
		contenu.montage?.audio
			? PisteAudio.pourFichier(username, contenu.date, contenu.montage.audio, contenu.montage.audio, null)
			: null
	);

	const pisteCategorie = (categorie: ContenuJournee['categories'][number], nom: string) =>
		PisteAudio.pourFichier(username, contenu.date, nom, null, categorie.categorie);

	const listes = (categorie: ContenuJournee['categories'][number]) =>
		[
			{ entete: 'À lire', liens: categorie.articles, classe: 'a-lire' },
			{ entete: 'À surveiller', liens: categorie.a_surveiller, classe: 'a-surveiller' }
		].filter((liste) => liste.liens.length);

	const cle = (lien: LienArticle, rang: number) => `${rang}-${lien.titre}`;
</script>

{#if contenu.en_cours}
	<p class="message" role="status">
		Cette journée est en cours de production : revenez dans quelques minutes.
	</p>
{:else if contenu.raison}
	<p class="attenue">{contenu.raison}</p>
{/if}

{#if montage}
	<div class="audio carte">
		<span>Journée{#if contenu.montage?.ecoute}<span class="attenue"> · {contenu.montage.ecoute}</span>{/if}</span>
		<LecteurPlein piste={montage} />
	</div>
{/if}

{#each contenu.categories as categorie, rang (rang)}
	<section class="carte">
		<h2>
			{categorie.categorie}{#if categorie.ecoute}<span class="attenue duree"> · {categorie.ecoute}</span>{/if}
		</h2>
		{#each paragraphes(categorie.resume) as paragraphe, i (i)}
			<p>{paragraphe}</p>
		{/each}
		{#each listes(categorie) as liste (liste.classe)}
			<h3 class={liste.classe}>{liste.entete}</h3>
			<ul>
				{#each liste.liens as lien, i (cle(lien, i))}
					{@const url = urlSure(lien.url)}
					<li>
						{#if url}
							<a href={url} rel="noopener noreferrer">{lien.titre}</a>
						{:else}
							<span>{lien.titre}</span>
						{/if}
						{#if lien.source}<span class="attenue"> — {lien.source}</span>{/if}
					</li>
				{/each}
			</ul>
		{/each}
		{#if categorie.audio && !contenu.montage}
			<div class="audio">
				<LecteurPlein piste={pisteCategorie(categorie, categorie.audio)} />
			</div>
		{/if}
	</section>
{/each}

<style>
	h2 {
		margin-top: 0;
	}

	.duree {
		font-size: 0.95rem;
		font-weight: 400;
	}

	h3 {
		font-size: 0.8rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		margin: 1.25rem 0 0.5rem;
	}

	.a-surveiller {
		color: var(--attenue);
	}

	ul {
		margin: 0;
		padding-left: 1.2rem;
	}

	li {
		margin-bottom: 0.4rem;
	}
</style>
