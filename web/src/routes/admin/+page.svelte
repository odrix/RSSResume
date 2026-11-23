<script lang="ts">
	import { LIBELLES_AVIS } from '#lib/retour.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const format = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
	const quand = (iso: string | null) => (iso ? format.format(new Date(iso)) : '—');
</script>

<svelte:head>
	<title>Administration — RSSResume</title>
</svelte:head>

<h1>Administration</h1>

{#if data.erreur}
	<p class="message erreur" role="alert">
		Profils indisponibles : {data.erreur} Seuls les comptes du site sont listés.
	</p>
{/if}

<p class="attenue">{data.lignes.length} profil(s) ou compte(s).</p>

<div class="table-defile">
	<table>
		<thead>
			<tr>
				<th scope="col">Utilisateur</th>
				<th scope="col">Compte</th>
				<th scope="col">Destinataires</th>
				<th scope="col">Inscrit</th>
				<th scope="col">Profil modifié</th>
				<th scope="col"><span class="visuellement-cache">Actions</span></th>
			</tr>
		</thead>
		<tbody>
			{#each data.lignes as ligne (ligne.username)}
				<tr>
					<td>
						<strong>{ligne.username}</strong>
						{#if ligne.prenom}<br /><span class="attenue">{ligne.prenom}</span>{/if}
					</td>
					<td>
						{#if ligne.emailCompte}
							{ligne.emailCompte}
							{#if ligne.admin}<br /><span class="attenue">admin</span>{/if}
							{#if !ligne.confirme}<br /><span class="attenue">en attente de confirmation</span>{/if}
						{:else}
							<span class="attenue">pas de compte</span>
						{/if}
					</td>
					<td>
						{#if ligne.modifieLe === null}
							<span class="attenue">pas de profil</span>
						{:else if ligne.emailsProfil.length}
							{ligne.emailsProfil.join(', ')}
						{:else}
							<span class="attenue">aucun</span>
						{/if}
					</td>
					<td>{quand(ligne.inscritLe)}</td>
					<td>{quand(ligne.modifieLe)}</td>
					<td><a href="/resumes/{encodeURIComponent(ligne.username)}">Résumés</a></td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<h2>Retours</h2>

{#if data.erreurRetours}
	<p class="message erreur" role="alert">Retours indisponibles : {data.erreurRetours}</p>
{:else if !data.retours.length}
	<p class="attenue">Aucun retour pour l'instant.</p>
{:else}
	<p class="attenue">{data.retours.length} retour(s), les plus récents d'abord.</p>
	<div class="table-defile">
		<table>
			<thead>
				<tr>
					<th scope="col">Reçu le</th>
					<th scope="col">Profil</th>
					<th scope="col">Journée</th>
					<th scope="col">Avis</th>
					<th scope="col">Commentaire</th>
				</tr>
			</thead>
			<tbody>
				{#each data.retours as retour, rang (rang)}
					<tr>
						<td>{quand(retour.vote_le)}</td>
						<td>
							{#if retour.username}{retour.username}{:else}<span class="attenue">profil supprimé</span>{/if}
						</td>
						<td>
							{#if retour.username}
								<a href="/resumes/{encodeURIComponent(retour.username)}/{retour.jour}">{retour.jour}</a>
							{:else}
								{retour.jour}
							{/if}
						</td>
						<td>{LIBELLES_AVIS[retour.avis]}</td>
						<td class="commentaire">{retour.commentaire}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	/* Le commentaire garde ses retours à la ligne, sans jamais être lu comme du balisage :
	 * Svelte l'échappe, le CSS seul le met en forme. */
	.commentaire {
		white-space: pre-wrap;
	}

	.visuellement-cache {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
	}
</style>
