<script lang="ts">
	import {
		AXES_PAR_DEFAUT,
		categoriesACocher,
		NOMBRE_MAX_AXES,
		NOMBRE_MIN_AXES,
		REGIMES,
		versLignes,
		versLignesAxes,
		type LigneStack,
		type ProfilSaisi
	} from '#lib/profil.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	/** Les champs sous lesquels un refus s'affiche. Un refus d'un autre champ — ou d'une
	 * section que la page ne montre pas — reste un message en tête de page. */
	const CHAMPS_AFFICHES = ['profil', 'prenom', 'email', 'securite', 'stack', 'axes'];

	// Après un refus, la page réaffiche ce qui a été saisi, pas ce qui est en base.
	const saisieRefusee = $derived(form && 'saisie' in form ? form.saisie : null);
	const source = $derived<ProfilSaisi | null>(saisieRefusee ?? data.depart);
	// Les adresses en attente restent dans la liste : enregistrer sans les retirer les garde
	// en attente, les effacer de la liste annule leur ajout.
	const adresses = $derived(
		saisieRefusee ? saisieRefusee.email : [...(data.depart?.email ?? []), ...data.enAttente]
	);

	const categoriesProposees = $derived(categoriesACocher(data.categories));
	const champRefuse = $derived.by(() => {
		if (!form || !('champ' in form) || !form.champ) return null;
		const affiches = categoriesProposees.length ? [...CHAMPS_AFFICHES, 'categories'] : CHAMPS_AFFICHES;
		return affiches.includes(form.champ) ? form.champ : null;
	});

	function erreurDe(champ: string): string | null {
		return champRefuse === champ && form && 'message' in form ? (form.message ?? null) : null;
	}

	/** Sans clé `categories`, le profil suit tout le catalogue : tout est coché. */
	function suivie(libelle: string): boolean {
		return source?.categories == null || source.categories.includes(libelle);
	}

	const exemple = $derived(
		data.gabarits.find((gabarit) => gabarit.metier === data.gabaritApplique?.metier) ?? data.gabarits[0]
	);
	const lignesAxes = $derived(versLignesAxes(source?.axes));
	const stackOuverte = $derived((source?.stack.length ?? 0) > 0 || erreurDe('stack') !== null);

	// Une ligne libre en fin de liste, pour qu'on puisse ajouter un composant même sans
	// JavaScript. Dérivée mais réassignable : les boutons la modifient, une nouvelle réponse
	// du serveur la recalcule. Les champs ne sont pas liés : la liste est indexée par
	// objet, chaque champ garde donc ce qu'on y a tapé quand une autre ligne disparaît.
	let lignes = $derived<LigneStack[]>([
		...versLignes(source?.stack ?? []),
		{ nom: '', alias: '' }
	]);

	function ajouter() {
		lignes = [...lignes, { nom: '', alias: '' }];
	}

	function retirer(ligne: LigneStack) {
		lignes = lignes.filter((autre) => autre !== ligne);
		if (!lignes.length) ajouter();
	}
</script>

<svelte:head>
	<title>Mon profil — RSSResume</title>
</svelte:head>

<h1>Mon profil</h1>

{#if form && 'enregistre' in form}
	<p class="message succes" role="status">
		Profil enregistré.
		{#if form.liensEnvoyes?.length}
			Un lien de confirmation a été envoyé à {form.liensEnvoyes.join(', ')} : l'adresse ne recevra
			le résumé qu'une fois ce lien ouvert.
		{/if}
	</p>
{/if}
{#if form && 'message' in form}
	<p class="message erreur" role="alert">
		{#if champRefuse}
			Le profil n'a pas été enregistré : le champ signalé ci-dessous est à corriger.
		{:else}
			{form.message}
		{/if}
	</p>
{:else if data.erreur}
	<p class="message erreur" role="alert">{data.erreur}</p>
{/if}

{#if data.gabarits.length}
	<form method="GET" action="/profil" class="carte repartir">
		<label for="gabarit">Repartir d'un gabarit</label>
		<span class="aide">
			Remplace le texte, le régime de sécurité, les rubriques{#if categoriesProposees.length} et les
				catégories{/if} par ceux d'un métier ; votre stack, vos adresses et votre prénom restent. Rien
			n'est enregistré avant « Enregistrer ».
		</span>
		<div class="ligne">
			<select id="gabarit" name="gabarit">
				{#each data.gabarits as gabarit (gabarit.metier)}
					<option value={gabarit.metier} selected={gabarit.metier === data.gabaritApplique?.metier}>
						{gabarit.libelle}
					</option>
				{/each}
			</select>
			<button type="submit" class="secondaire">Pré-remplir</button>
		</div>
	</form>
{/if}

{#if data.gabaritApplique && !saisieRefusee}
	<p class="message annonce" role="status">
		Formulaire pré-rempli avec le gabarit « {data.gabaritApplique.libelle} » :
		{#if data.gabaritApplique.categories}
			texte, régime, rubriques et catégories.
		{:else}
			texte, régime et rubriques ; vos catégories ne changent pas.
		{/if}
		Rien n'est enregistré tant que vous n'avez pas cliqué sur « Enregistrer ».
	</p>
{/if}

<!-- L'action est explicite : sans elle, le POST garderait `?gabarit=` dans l'adresse, et la
     page rechargée après l'enregistrement ré-appliquerait le gabarit. -->
<form method="POST" action="/profil" class="formulaire large carte">
	<div class="champ">
		<label for="profil">Profil de veille</label>
		<span class="aide">
			Écrivez-le comme à un collègue qui ferait votre veille à votre place. Les trois étapes du
			résumé le lisent — la notation, le résumé de chaque article, l'audio. Trois paragraphes
			suffisent :
		</span>
		<ul class="aide rubriques">
			<li><strong>Mon métier</strong> — ce que vous faites, et dans quel contexte.</li>
			<li><strong>Ce que je veux suivre</strong> — les sujets qui vous font agir ou décider.</li>
			<li><strong>Ce qui ne m'intéresse pas</strong> — ce qui encombre sans rien vous apprendre.</li>
		</ul>
		{#if exemple}
			<details class="exemple">
				<summary class="aide">Exemple : le gabarit « {exemple.libelle} »</summary>
				<p class="aide">{exemple.profil}</p>
			</details>
		{/if}
		<textarea
			id="profil"
			name="profil"
			rows="14"
			required
			aria-invalid={erreurDe('profil') ? 'true' : undefined}
			aria-describedby={erreurDe('profil') ? 'erreur-profil' : undefined}
		>{source?.profil ?? ''}</textarea>
		{#if erreurDe('profil')}<span class="erreur-champ" id="erreur-profil">{erreurDe('profil')}</span>{/if}
	</div>

	{#if data.categories?.ouvert}
		<fieldset class="bloc">
			<legend><strong>Catégories suivies</strong></legend>
			<p class="aide">Aucun catalogue n'est déclaré sur ce service : toutes les catégories sont suivies.</p>
		</fieldset>
	{:else if categoriesProposees.length}
		<fieldset class="bloc categories">
			<legend><strong>Catégories suivies</strong></legend>
			<p class="aide">
				Ce qui n'est pas coché n'est ni noté ni résumé pour vous. Tout coché : vous suivrez aussi les
				catégories ajoutées plus tard.
			</p>
			<input type="hidden" name="categories_editees" value="1" />
			{#each categoriesProposees as categorie (categorie.libelle)}
				<input type="hidden" name="categories_proposees" value={categorie.libelle} />
				<label class="case">
					<input
						type="checkbox"
						name="categories"
						value={categorie.libelle}
						checked={suivie(categorie.libelle)}
						aria-invalid={erreurDe('categories') ? 'true' : undefined}
						aria-describedby={erreurDe('categories') ? 'erreur-categories' : undefined}
					/>
					<span>
						{categorie.libelle}{#if categorie.privee}<span class="aide privee">(privée, montrée à vous seul)</span>{/if}
						<span class="aide description">{categorie.description}</span>
					</span>
				</label>
			{/each}
			{#if erreurDe('categories')}
				<span class="erreur-champ" id="erreur-categories">{erreurDe('categories')}</span>
			{/if}
		</fieldset>
	{/if}

	<fieldset
		class="bloc"
		role="radiogroup"
		aria-invalid={erreurDe('securite') ? 'true' : undefined}
		aria-describedby={erreurDe('securite') ? 'erreur-securite' : undefined}
	>
		<legend><strong>Régime de sécurité</strong></legend>
		<p class="aide">Ce que vous avez besoin d'entendre d'une faille de sécurité.</p>
		{#each REGIMES as regime (regime.valeur)}
			<label class="case">
				<input
					type="radio"
					name="securite"
					value={regime.valeur}
					checked={(source?.securite ?? 'exploitant') === regime.valeur}
				/>
				<span>{regime.libelle} <span class="aide">— {regime.explication}</span></span>
			</label>
		{/each}
		{#if erreurDe('securite')}<span class="erreur-champ" id="erreur-securite">{erreurDe('securite')}</span>{/if}
	</fieldset>

	<fieldset class="bloc">
		<legend><strong>Rubriques du résumé</strong> <span class="aide">(facultatif)</span></legend>
		<p class="aide">
			Les rubriques entre lesquelles vos articles sont rangés, de {NOMBRE_MIN_AXES} à {NOMBRE_MAX_AXES} :
			un nom court, et ce qu'elle couvre. La dernière reçoit ce qui ne va nulle part ailleurs. Toutes
			vides : les rubriques par défaut ({AXES_PAR_DEFAUT.join(', ')}).
		</p>
		<input type="hidden" name="axes_edites" value="1" />
		{#each lignesAxes as ligne, rang (rang)}
			<div class="axe-ligne">
				<input type="hidden" name="axe_slug" value={ligne.slug} />
				<input
					name="axe_libelle"
					placeholder="Nom, ex. Qualité"
					aria-label="Nom de la rubrique {rang + 1}"
					value={ligne.libelle}
					aria-invalid={erreurDe('axes') ? 'true' : undefined}
					aria-describedby={erreurDe('axes') ? 'erreur-axes' : undefined}
				/>
				<input
					name="axe_description"
					placeholder="Ce qu'elle couvre, ex. tests, revue de code, outillage"
					aria-label="Ce que couvre la rubrique {rang + 1}"
					value={ligne.description}
					aria-invalid={erreurDe('axes') ? 'true' : undefined}
					aria-describedby={erreurDe('axes') ? 'erreur-axes' : undefined}
				/>
			</div>
		{/each}
		{#if erreurDe('axes')}<span class="erreur-champ" id="erreur-axes">{erreurDe('axes')}</span>{/if}
	</fieldset>

	<label>
		Prénom <span class="aide">(facultatif — la salutation de l'audio)</span>
		<input
			name="prenom"
			autocomplete="given-name"
			value={source?.prenom ?? ''}
			aria-invalid={erreurDe('prenom') ? 'true' : undefined}
		/>
		{#if erreurDe('prenom')}<span class="erreur-champ">{erreurDe('prenom')}</span>{/if}
	</label>

	<label>
		Adresses de réception
		<span class="aide">
			Une par ligne. Une adresse ajoutée reçoit d'abord un lien de confirmation ; une adresse
			retirée ne reçoit plus rien dès l'enregistrement. Vide, aucun email ne part.
		</span>
		<textarea name="email" rows="3" aria-invalid={erreurDe('email') ? 'true' : undefined}
			>{adresses.join('\n')}</textarea
		>
		{#if erreurDe('email')}<span class="erreur-champ">{erreurDe('email')}</span>{/if}
		{#if !saisieRefusee && data.enAttente.length}
			<span class="aide">En attente de confirmation : {data.enAttente.join(', ')}</span>
		{/if}
	</label>

	<details class="bloc stack" open={stackOuverte}>
		<summary>
			<strong>Stack surveillée</strong>
			<span class="aide">(facultatif) — si vous exploitez des serveurs ou des logiciels</span>
		</summary>
		<p class="aide">
			Les logiciels que vous faites tourner : les avis de sécurité officiels qui les citent vous sont
			signalés. Les alias sont les autres noms du même logiciel, séparés par des virgules. Vide, rien
			n'est signalé.
		</p>
		{#each lignes as ligne (ligne)}
			<div class="stack-ligne">
				<input
					name="stack_nom"
					placeholder="Logiciel, ex. PostgreSQL"
					aria-label="Logiciel"
					value={ligne.nom}
					aria-invalid={erreurDe('stack') ? 'true' : undefined}
				/>
				<input name="stack_alias" placeholder="Alias, ex. Postgres" aria-label="Alias" value={ligne.alias} />
				<button type="button" class="secondaire" onclick={() => retirer(ligne)} aria-label="Retirer ce logiciel">
					Retirer
				</button>
			</div>
		{/each}
		<button type="button" class="secondaire" onclick={ajouter}>Ajouter un logiciel</button>
		{#if erreurDe('stack')}<span class="erreur-champ">{erreurDe('stack')}</span>{/if}
	</details>

	<button type="submit">Enregistrer</button>
</form>

<style>
	.champ {
		display: grid;
		gap: 0.3rem;
	}

	.bloc {
		display: grid;
		gap: 0.5rem;
		border: 1px solid var(--bord);
		border-radius: var(--rayon);
		padding: 0.75rem 1rem 1rem;
		margin: 0;
	}

	.bloc p {
		margin: 0;
	}

	.rubriques {
		margin: 0;
		padding-left: 1.25rem;
	}

	.exemple p {
		white-space: pre-line;
		margin: 0.5rem 0 0;
	}

	summary {
		cursor: pointer;
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

	.description {
		display: block;
	}

	.privee {
		margin-left: 0.35em;
	}

	.axe-ligne {
		display: grid;
		grid-template-columns: 1fr 2fr;
		gap: 0.5rem;
	}

	.repartir {
		display: grid;
		gap: 0.3rem;
	}

	.repartir .ligne {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.message.annonce {
		background: var(--surface);
		border: 1px solid var(--bord);
	}

	@media (max-width: 32rem) {
		.axe-ligne {
			grid-template-columns: 1fr;
		}
	}
</style>
