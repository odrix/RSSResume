<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const echec = $derived(form && 'champ' in form ? form : null);
	const envoye = $derived(form && 'envoye' in form ? form.envoye : null);
	const erreur = (champ: string) => (echec?.champ === champ ? echec.message : null);
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

	<label>
		Votre profil de veille
		<span class="aide">
			Décrivez votre métier et ce que vous voulez suivre. Ce texte décide des articles retenus ; vous
			pourrez le modifier ensuite.
		</span>
		<textarea
			name="profil"
			rows="10"
			aria-invalid={erreur('profil') ? 'true' : undefined}
			>{echec?.valeurs?.profil ?? data.profilParDefaut}</textarea
		>
		{#if erreur('profil')}<span class="erreur-champ">{erreur('profil')}</span>{/if}
	</label>

	<button type="submit">Créer mon compte</button>
	<p class="attenue">Déjà inscrit ? <a href="/connexion">Se connecter</a></p>
</form>
{/if}
