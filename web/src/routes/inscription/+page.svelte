<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const echec = $derived(form && 'champ' in form ? form : null);
	const envoye = $derived(form && 'envoye' in form ? form.envoye : null);
	const erreur = (champ: string) => (echec?.champ === champ ? echec.message : null);

	/** Le texte proposé pour un métier : celui du gabarit, ou le texte général pour « Autre ». */
	const texteDe = (metier: string) =>
		metier === 'autre' ? data.profilParDefaut : (data.gabarits.find((g) => g.metier === metier)?.profil ?? '');

	// Dérivés mais réassignables : le choix du métier les modifie, une nouvelle réponse du
	// serveur les recalcule. Sans JavaScript, la zone part vide et le serveur y met le texte
	// du métier choisi : un texte pré-rempli serait envoyé tel quel, même après avoir changé
	// de métier. API muette : pas de liste, le texte général comme avant les gabarits.
	let metier = $derived(echec?.valeurs?.metier ?? data.metier);
	let texte = $derived(echec?.valeurs?.profil ?? (data.indisponible ? data.profilParDefaut : ''));
	const choisi = $derived(data.gabarits.find((g) => g.metier === metier) ?? null);

	function choisir(nouveau: string) {
		metier = nouveau;
		// Remplacer plutôt que garder : le texte d'un autre métier n'a plus de sens ici, et
		// l'aide sous la zone prévient qu'un changement efface la saisie.
		texte = texteDe(nouveau);
	}

	// Un métier présélectionné par le lien (`?metier=`) : son texte, une fois la page active.
	onMount(() => {
		if (!texte && metier) texte = texteDe(metier);
	});
</script>

<svelte:head>
	<title>Créer un compte — RSSResume</title>
</svelte:head>

<h1>Créer un compte</h1>

{#if envoye}
	<div class="carte" role="status">
		<p>
			Un lien de confirmation vient d'être envoyé à <strong>{envoye}</strong>. Ouvrez-le dans les
			24 heures pour activer votre compte.
		</p>
		<p class="attenue">
			Rien reçu ? Vérifiez les indésirables, ou <a href="/renvoyer-lien?email={encodeURIComponent(envoye)}"
				>demandez un nouveau lien</a
			>.
		</p>
	</div>
{:else}
{#if erreur('general')}
	<p class="message erreur" role="alert">{erreur('general')}</p>
{/if}

<form method="POST" class="formulaire carte" novalidate>
	<label>
		Adresse email
		<input
			type="email"
			name="email"
			autocomplete="email"
			required
			value={echec?.valeurs?.email ?? ''}
			aria-invalid={erreur('email') ? 'true' : undefined}
		/>
		{#if erreur('email')}<span class="erreur-champ">{erreur('email')}</span>{/if}
	</label>

	<label>
		Nom d'utilisateur
		<span class="aide">2 à 32 caractères : minuscules, chiffres, « _ » ou « - ».</span>
		<input
			name="username"
			autocomplete="username"
			required
			pattern={'[a-z0-9][a-z0-9_\\-]{1,31}'}
			value={echec?.valeurs?.username ?? ''}
			aria-invalid={erreur('username') ? 'true' : undefined}
		/>
		{#if erreur('username')}<span class="erreur-champ">{erreur('username')}</span>{/if}
	</label>

	<label>
		Mot de passe
		<span class="aide">Au moins 12 caractères. Une phrase fait très bien l'affaire.</span>
		<input
			type="password"
			name="motDePasse"
			autocomplete="new-password"
			minlength="12"
			required
			aria-invalid={erreur('motDePasse') ? 'true' : undefined}
		/>
		{#if erreur('motDePasse')}<span class="erreur-champ">{erreur('motDePasse')}</span>{/if}
	</label>

	<label>
		Prénom <span class="aide">(facultatif — la salutation de l'audio)</span>
		<input name="prenom" autocomplete="given-name" value={echec?.valeurs?.prenom ?? ''} />
	</label>

	{#if data.indisponible}
		<input type="hidden" name="metier" value="autre" />
	{:else}
		<label>
			Votre métier
			<span class="aide">Il donne le point de départ de votre profil : le texte, les rubriques, les catégories suivies.</span>
			<select
				name="metier"
				required
				onchange={(e) => choisir(e.currentTarget.value)}
				aria-invalid={erreur('metier') ? 'true' : undefined}
			>
				<option value="" disabled selected={!metier}>Votre métier</option>
				{#each data.gabarits as gabarit (gabarit.metier)}
					<option value={gabarit.metier} selected={metier === gabarit.metier}>{gabarit.libelle}</option>
				{/each}
				<option value="autre" selected={metier === 'autre'}>Autre : je décris mon métier</option>
			</select>
			{#if choisi}
				<span class="aide">Catégories suivies : {choisi.categories.join(', ')}</span>
			{:else if metier === 'autre'}
				<span class="aide">Catégories suivies : toutes les catégories ouvertes.</span>
			{/if}
			{#if erreur('metier')}<span class="erreur-champ">{erreur('metier')}</span>{/if}
		</label>
	{/if}

	<label>
		Votre profil de veille
		<span class="aide">
			Ce texte décide des articles retenus : relisez-le, retouchez-le ; vous pourrez le modifier
			ensuite.{#if !data.indisponible} Changer de métier le remplace par celui du métier choisi.{/if}
		</span>
		<textarea
			name="profil"
			rows="10"
			bind:value={texte}
			placeholder="Choisissez votre métier : son texte de départ sera retenu si vous laissez cette zone vide."
			aria-invalid={erreur('profil') ? 'true' : undefined}
		></textarea>
		{#if erreur('profil')}<span class="erreur-champ">{erreur('profil')}</span>{/if}
	</label>

	<button type="submit">Créer mon compte</button>
	<p class="attenue">Déjà inscrit ? <a href="/connexion">Se connecter</a></p>
</form>
{/if}
