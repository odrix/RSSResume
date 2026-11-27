<script lang="ts">
	import { LIBELLES_AVIS } from '#lib/retour.js';
	import { REGIMES, type Securite } from '#lib/profil.js';
	import Camembert from './Camembert.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const format = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });
	const quand = (iso: string | null) => (iso ? format.format(new Date(iso)) : '-');

	type PeriodeCouts = { total: number | null; devise: string; tarification_complete: boolean; modeles_sans_tarif: string[] };

	// Un coût inconnu vaut 0 plutôt qu'un « ? » : mieux que rien. Les modèles sans tarif
	// restent signalés à côté, pour ne pas faire croire à une tarification complète.
	const cout = (couts: PeriodeCouts | null) => {
		if (!couts) return { montant: '0', devise: '', note: '' };
		const note = couts.tarification_complete ? '' : `tarif partiel : ${couts.modeles_sans_tarif.join(', ')}`;
		return { montant: (couts.total ?? 0).toFixed(6), devise: couts.devise, note };
	};

	// Le coût par résumé divise par les journées produites de la période ; sans journée,
	// le coût par résumé est 0, pas une division par zéro.
	const coutParResume = (couts: PeriodeCouts | null, journees: number) => {
		if (!couts || !journees) return { montant: '0.000000', devise: couts?.devise ?? '' };
		return { montant: ((couts.total ?? 0) / journees).toFixed(6), devise: couts.devise };
	};

	const libelleSecurite = (valeur: string) => REGIMES.find((regime) => regime.valeur === (valeur as Securite))?.libelle ?? valeur;

	const tranchesSecurite = $derived(
		data.repartitionSecurite.map((tranche) => ({ ...tranche, libelle: libelleSecurite(tranche.libelle) }))
	);

	const onglets = [
		{ id: 'profils', libelle: 'Liste des profils', href: '/admin' },
		{ id: 'stats', libelle: 'Stats', href: '/admin?onglet=stats' },
		{ id: 'retours', libelle: 'Retours', href: '/admin?onglet=retours' }
	] as const;

	const maxCategories = $derived(Math.max(1, ...data.parCategorie.map((tranche) => tranche.nombre)));
</script>

<svelte:head>
	<title>Administration, RSSResume</title>
</svelte:head>

<h1>Administration</h1>

<nav class="onglets" aria-label="Sections de l'administration">
	{#each onglets as onglet (onglet.id)}
		<a href={onglet.href} class:actif={data.onglet === onglet.id} aria-current={data.onglet === onglet.id ? 'page' : undefined}>
			{onglet.libelle}
		</a>
	{/each}
</nav>

{#if data.erreur}
	<p class="message erreur" role="alert">
		Profils indisponibles : {data.erreur} Seuls les comptes du site sont listés.
	</p>
{/if}

{#if data.onglet === 'profils'}
	<p class="attenue">{data.lignes.length} profil(s) ou compte(s).</p>

	<div class="table-defile">
		<table class="ligne-unique">
			<thead>
				<tr>
					<th scope="col">Utilisateur</th>
					<th scope="col">Compte</th>
					<th scope="col">Destinataires</th>
					<th scope="col">Profil</th>
					<th scope="col">Sécurité</th>
					<th scope="col">Catégories</th>
					<th scope="col">Inscrit</th>
					<th scope="col">Profil modifié</th>
					<th scope="col">Dernière connexion</th>
					<th scope="col">Consultations 7 j</th>
					<th scope="col">Journées 7 j</th>
					<th scope="col">Journées 30 j</th>
					<th scope="col">Coût 7 j</th>
					<th scope="col">Coût 30 j</th>
					<th scope="col">Coût/résumé 7 j</th>
					<th scope="col">Coût/résumé 30 j</th>
					<th scope="col">État email</th>
					<th scope="col"><span class="visuellement-cache">Actions</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.lignes as ligne (ligne.username)}
					{@const c7 = cout(ligne.couts7j)}
					{@const c30 = cout(ligne.couts30j)}
					{@const par7 = coutParResume(ligne.couts7j, ligne.journees7j)}
					{@const par30 = coutParResume(ligne.couts30j, ligne.journees30j)}
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
						<td>{ligne.profilChoisi ?? '-'}</td>
						<td>{ligne.securite ? libelleSecurite(ligne.securite) : '-'}</td>
						<td>{ligne.categoriesLibelles === null ? (ligne.modifieLe === null ? '-' : 'toutes') : ligne.categoriesLibelles.length}</td>
						<td>{quand(ligne.inscritLe)}</td>
						<td>{quand(ligne.modifieLe)}</td>
						<td>{quand(ligne.derniereConnexionLe)}</td>
						<td>{ligne.consultations7j}</td>
						<td>{ligne.journees7j}</td>
						<td>{ligne.journees30j}</td>
						<td>
							{c7.montant} {c7.devise}
							{#if c7.note}<br /><span class="attenue">{c7.note}</span>{/if}
						</td>
						<td>
							{c30.montant} {c30.devise}
							{#if c30.note}<br /><span class="attenue">{c30.note}</span>{/if}
						</td>
						<td>{par7.montant} {par7.devise}</td>
						<td>{par30.montant} {par30.devise}</td>
						<td>{ligne.desabonne ? 'désabonné' : ligne.modifieLe === null ? 'sans profil' : 'actif'}</td>
						<td><a href="/resumes/{encodeURIComponent(ligne.username)}">Résumés</a></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else if data.onglet === 'stats'}
	<h2>Usage de la semaine</h2>
	<ul>
		<li>{data.inscriptions7j} inscription(s) confirmée(s) sur 7 jours</li>
		<li>{data.inscriptions30j} inscription(s) confirmée(s) sur 30 jours</li>
		<li>
			Coût total des 7 derniers jours : {data.coutTotalSemaine.toFixed(6)} {data.deviseSemaine ?? ''}
			{#if data.modelesSansTarifSemaine.length}
				<span class="attenue">(tarif partiel : {data.modelesSansTarifSemaine.join(', ')})</span>
			{/if}
		</li>
	</ul>
	<p class="attenue">Les écoutes depuis l’email ou l’audio ne sont pas encore comptées : elles seront disponibles avec BL-075. Les consultations sont celles ouvertes sur le site.</p>

	<h2>Répartition</h2>
	<div class="camemberts">
		<Camembert titre="Profils choisis" tranches={data.repartitionProfils} />
		<Camembert titre="Types de sécurité" tranches={tranchesSecurite} />
	</div>

	<h2>Catégories suivies</h2>
	{#if !data.parCategorie.length}
		<p class="attenue">Aucun profil.</p>
	{:else}
		<table class="categories">
			<thead>
				<tr><th scope="col">Catégorie</th><th scope="col">Personnes</th><th scope="col"><span class="visuellement-cache">Répartition</span></th></tr>
			</thead>
			<tbody>
				{#each data.parCategorie as tranche (tranche.libelle)}
					<tr>
						<td>{tranche.libelle}</td>
						<td>{tranche.nombre}</td>
						<td class="barre-cellule">
							<div class="barre" style="width: {(tranche.nombre / maxCategories) * 100}%"></div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{:else}
	<h2>Retours</h2>

	{#if data.erreurRetours}
		<p class="message erreur" role="alert">Retours indisponibles : {data.erreurRetours}</p>
	{:else if !data.retours.length}
		<p class="attenue">Aucun retour pour l'instant.</p>
	{:else}
		<p class="attenue">{data.retours.length} retour(s), les plus récents d'abord.</p>
		<div class="table-defile">
			<table class="ligne-unique">
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
{/if}

<style>
	.onglets {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.onglets a {
		padding: 0.45rem 0.9rem;
		border: 3px solid var(--bord);
		background: var(--surface);
		color: var(--texte);
		text-decoration: none;
		box-shadow: var(--ombre);
	}

	.onglets a.actif {
		background: var(--texte);
		color: var(--surface);
	}

	/* Les valeurs tiennent sur une seule ligne : le tableau défile horizontalement
	 * plutôt que de couper les adresses, les dates ou les coûts. */
	.ligne-unique th,
	.ligne-unique td {
		white-space: nowrap;
	}

	.ligne-unique .commentaire {
		white-space: pre-wrap;
	}

	.camemberts {
		display: flex;
		gap: 1.5rem;
		flex-wrap: wrap;
		margin-bottom: 2rem;
	}

	.categories {
		max-width: 40rem;
	}

	.barre-cellule {
		width: 40%;
	}

	.barre {
		height: 0.9rem;
		background: var(--texte);
		min-width: 2px;
	}

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
