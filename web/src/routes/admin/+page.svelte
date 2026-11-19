<script lang="ts">
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

<style>
	.visuellement-cache {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
	}
</style>
