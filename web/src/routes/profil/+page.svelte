<script lang="ts">
	import { versLignes, type LigneStack, type ProfilSaisi } from '#lib/profil.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	// Après un refus, la page réaffiche ce qui a été saisi, pas ce qui est en base.
	const saisieRefusee = $derived(form && 'saisie' in form ? form.saisie : null);
	const source = $derived<ProfilSaisi | null>(saisieRefusee ?? data.profil);
	// Les adresses en attente restent dans la liste : enregistrer sans les retirer les garde
	// en attente, les effacer de la liste annule leur ajout.
	const adresses = $derived(
		saisieRefusee ? saisieRefusee.email : [...(data.profil?.email ?? []), ...data.enAttente]
	);

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
	<p class="message erreur" role="alert">{form.message}</p>
{:else if data.erreur}
	<p class="message erreur" role="alert">{data.erreur}</p>
{/if}

<form method="POST" class="formulaire large carte">
	<label>
		Profil de veille
		<span class="aide">
			Votre métier, vos axes de veille, ce qui ne vous intéresse pas. Les trois étapes du résumé le
			lisent : la notation, le résumé de chaque article, l'audio.
		</span>
		<textarea name="profil" rows="14" required>{source?.profil ?? ''}</textarea>
	</label>

	<label>
		Prénom <span class="aide">(facultatif — la salutation de l'audio)</span>
		<input name="prenom" autocomplete="given-name" value={source?.prenom ?? ''} />
	</label>

	<label>
		Adresses de réception
		<span class="aide">
			Une par ligne. Une adresse ajoutée reçoit d'abord un lien de confirmation ; une adresse
			retirée ne reçoit plus rien dès l'enregistrement. Vide, aucun email ne part.
		</span>
		<textarea name="email" rows="3">{adresses.join('\n')}</textarea>
		{#if !saisieRefusee && data.enAttente.length}
			<span class="aide">En attente de confirmation : {data.enAttente.join(', ')}</span>
		{/if}
	</label>

	<fieldset class="stack">
		<legend><strong>Stack surveillée</strong></legend>
		<p class="aide">
			Les composants que vous exploitez : les avis de sécurité CERT-FR qui les citent sont signalés.
			Les alias sont les autres noms du même composant, séparés par des virgules.
		</p>
		{#each lignes as ligne (ligne)}
			<div class="stack-ligne">
				<input name="stack_nom" placeholder="Composant, ex. Keycloak" aria-label="Composant" value={ligne.nom} />
				<input name="stack_alias" placeholder="Alias, ex. RH-SSO" aria-label="Alias" value={ligne.alias} />
				<button type="button" class="secondaire" onclick={() => retirer(ligne)} aria-label="Retirer ce composant">
					Retirer
				</button>
			</div>
		{/each}
		<button type="button" class="secondaire" onclick={ajouter}>Ajouter un composant</button>
	</fieldset>

	<button type="submit">Enregistrer</button>
</form>

<style>
	.stack {
		border: 1px solid var(--bord);
		border-radius: var(--rayon);
		padding: 0.75rem 1rem 1rem;
		margin: 0;
	}
</style>
