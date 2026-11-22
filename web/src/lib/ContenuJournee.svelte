<!--
	Ce qu'une journée raconte : l'audio, puis par catégorie le résumé et ses articles.

	Tout passe par des expressions `{…}`, que Svelte échappe : le résumé vient du modèle, les
	titres et les sources des flux, et aucun d'eux n'est fiable. Jamais de bloc `@html`. Les liens ne
	deviennent des `href` qu'après `urlSure`, l'échappement ne protégeant pas d'un `javascript:`.
-->
<script lang="ts">
	import { paragraphes, urlSure, type ContenuJournee, type LienArticle } from '#lib/journee.js';

	let { contenu, username }: { contenu: ContenuJournee; username: string } = $props();

	/** La même URL que les lecteurs de la liste : le relais du site, jamais l'API. */
	const urlAudio = (nom: string) =>
		`/audio/${encodeURIComponent(username)}/${encodeURIComponent(contenu.date)}/${encodeURIComponent(nom)}`;

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

{#if contenu.montage?.audio}
	<div class="audio carte">
		<span>Journée{#if contenu.montage.ecoute}<span class="attenue"> · {contenu.montage.ecoute}</span>{/if}</span>
		<audio controls preload="none" src={urlAudio(contenu.montage.audio)}></audio>
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
				<audio controls preload="none" src={urlAudio(categorie.audio)}></audio>
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
