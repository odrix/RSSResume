<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const format = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
	const quand = (iso: string | null) => (iso ? format.format(new Date(iso)) : '—');
	const cout = (couts: { total: number | null; devise: string; tarification_complete: boolean; modeles_sans_tarif: string[] } | null) => {
		if (!couts) return '—';
		if (!couts.tarification_complete) return `? (${couts.modeles_sans_tarif.join(', ')})`;
		return `${couts.total?.toFixed(6) ?? '0.000000'} ${couts.devise}`;
	};
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
				<th scope="col">Dernière connexion</th>
				<th scope="col">Consultations 7 j</th>
				<th scope="col">État email</th>
				<th scope="col">Coût 7 j</th>
				<th scope="col">Coût 30 j</th>
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
					<td>{quand(ligne.derniereConnexionLe)}</td>
					<td>{ligne.consultations7j}</td>
					<td>{ligne.desabonne ? 'désabonné' : ligne.modifieLe === null ? 'sans profil' : 'actif'}</td>
					<td>{cout(ligne.couts7j)}</td>
					<td>{cout(ligne.couts30j)}</td>
					<td><a href="/resumes/{encodeURIComponent(ligne.username)}">Résumés</a></td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<h2>Usage de la semaine</h2>
<ul>
	<li>{data.inscriptions7j} inscription(s) confirmée(s) sur 7 jours</li>
	<li>{data.inscriptions30j} inscription(s) confirmée(s) sur 30 jours</li>
	<li>Coût total des 7 derniers jours : {data.coutTotalSemaine === null ? `? (${data.modelesSansTarifSemaine.join(', ') || 'tarification incomplète'})` : `${data.coutTotalSemaine.toFixed(6)} ${data.deviseSemaine ?? ''}`}</li>
</ul>
<p class="attenue">Les écoutes depuis l’email ou l’audio ne sont pas encore comptées : elles seront disponibles avec BL-075. Les retours « utile / pas utile » seront disponibles avec BL-079. Les consultations ci-dessous sont celles ouvertes sur le site.</p>

<style>
	.visuellement-cache {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
	}
</style>
