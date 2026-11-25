<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	/** Le message d'un champ, seulement sous le formulaire qui a été envoyé. */
	function erreur(formulaire: string, champ: string): string | null {
		if (!form || !('champ' in form) || form.formulaire !== formulaire || form.champ !== champ) return null;
		return form.message ?? null;
	}

	function messageGeneral(formulaire: string): string | null {
		return erreur(formulaire, 'general');
	}

	function succes(formulaire: string): string | null {
		return form && 'succes' in form && form.formulaire === formulaire ? (form.succes ?? null) : null;
	}
</script>

<svelte:head>
	<title>Mon compte — RSSResume</title>
</svelte:head>

<h1>Mon compte</h1>

<p class="attenue">
	Ce qui sert à vous connecter. Les adresses qui reçoivent le résumé quotidien se règlent dans
	<a href="/profil">Mon profil</a>.
</p>

<h2>Mot de passe</h2>

{#if succes('motDePasse')}
	<p class="message succes" role="status">{succes('motDePasse')}</p>
{/if}

<form method="POST" action="?/motDePasse" class="formulaire carte">
	<label>
		Mot de passe actuel
		<input
			type="password"
			name="motDePasseActuel"
			autocomplete="current-password"
			required
			aria-invalid={erreur('motDePasse', 'motDePasseActuel') ? 'true' : undefined}
		/>
		{#if erreur('motDePasse', 'motDePasseActuel')}
			<span class="erreur-champ">{erreur('motDePasse', 'motDePasseActuel')}</span>
		{/if}
	</label>
	<label>
		Nouveau mot de passe
		<span class="aide">Au moins 12 caractères. Vos autres sessions seront fermées.</span>
		<input
			type="password"
			name="nouveauMotDePasse"
			autocomplete="new-password"
			minlength="12"
			required
			aria-invalid={erreur('motDePasse', 'nouveauMotDePasse') ? 'true' : undefined}
		/>
		{#if erreur('motDePasse', 'nouveauMotDePasse')}
			<span class="erreur-champ">{erreur('motDePasse', 'nouveauMotDePasse')}</span>
		{/if}
	</label>
	<button type="submit">Changer le mot de passe</button>
</form>

<h2>Adresse de connexion</h2>

{#if succes('adresse')}
	<p class="message succes" role="status">{succes('adresse')}</p>
{:else if messageGeneral('adresse')}
	<p class="message erreur" role="alert">{messageGeneral('adresse')}</p>
{/if}

<form method="POST" action="?/adresse" class="formulaire carte">
	<p>Adresse actuelle : <strong>{data.email}</strong></p>
	<label>
		Nouvelle adresse
		<span class="aide">Elle reçoit un lien : le changement ne vaut qu'une fois ce lien ouvert.</span>
		<input
			type="email"
			name="email"
			autocomplete="email"
			required
			value={form && 'email' in form ? form.email : ''}
			aria-invalid={erreur('adresse', 'email') ? 'true' : undefined}
		/>
		{#if erreur('adresse', 'email')}<span class="erreur-champ">{erreur('adresse', 'email')}</span>{/if}
	</label>
	<label>
		Mot de passe actuel
		<input
			type="password"
			name="motDePasse"
			autocomplete="current-password"
			required
			aria-invalid={erreur('adresse', 'motDePasseActuel') ? 'true' : undefined}
		/>
		{#if erreur('adresse', 'motDePasseActuel')}
			<span class="erreur-champ">{erreur('adresse', 'motDePasseActuel')}</span>
		{/if}
	</label>
	<button type="submit">Changer d'adresse</button>
</form>
