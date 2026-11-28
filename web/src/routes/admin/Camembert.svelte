<script lang="ts">
	interface Tranche {
		libelle: string;
		nombre: number;
	}

	let { tranches, titre }: { tranches: Tranche[]; titre: string } = $props();

	// Une palette fixe, assez contrastée pour se lire aussi en niveaux de gris.
	const PALETTE = ['#5f72a0', '#c9a227', '#7a9e7e', '#b0563f', '#6b8cae', '#8e6fa8', '#a8763e', '#4f8a8b'];

	const CENTRE = 100;
	const RAYON = 80;

	const total = $derived(tranches.reduce((somme, tranche) => somme + tranche.nombre, 0));

	interface Part {
		libelle: string;
		nombre: number;
		couleur: string;
		/** Chemin SVG de la part, ou `null` pour un camembert plein (une seule part). */
		chemin: string | null;
	}

	const parts = $derived.by(() => {
		const resultat: Part[] = [];
		let angle = -Math.PI / 2;
		for (const [rang, tranche] of tranches.entries()) {
			if (!tranche.nombre) continue;
			const part = tranche.nombre / total;
			const couleur = PALETTE[rang % PALETTE.length];
			if (tranche.nombre === total) {
				resultat.push({ ...tranche, couleur, chemin: null });
				break;
			}
			const fin = angle + part * 2 * Math.PI;
			const x0 = CENTRE + RAYON * Math.cos(angle);
			const y0 = CENTRE + RAYON * Math.sin(angle);
			const x1 = CENTRE + RAYON * Math.cos(fin);
			const y1 = CENTRE + RAYON * Math.sin(fin);
			const grand = part > 0.5 ? 1 : 0;
			resultat.push({
				...tranche,
				couleur,
				chemin: `M ${CENTRE} ${CENTRE} L ${x0.toFixed(3)} ${y0.toFixed(3)} A ${RAYON} ${RAYON} 0 ${grand} 1 ${x1.toFixed(3)} ${y1.toFixed(3)} Z`
			});
			angle = fin;
		}
		return resultat;
	});

	const pourcentage = (nombre: number) => (total ? Math.round((nombre / total) * 100) : 0);
</script>

<section class="camembert" aria-label={titre}>
	<h3>{titre}</h3>
	{#if !total}
		<p class="attenue">Aucune donnée.</p>
	{:else}
		<div class="ensemble">
			<svg viewBox="0 0 200 200" role="img" aria-label={titre}>
				{#each parts as part (part.libelle)}
					{#if part.chemin}
						<path d={part.chemin} fill={part.couleur} stroke="var(--surface)" stroke-width="1.5" />
					{:else}
						<circle cx={CENTRE} cy={CENTRE} r={RAYON} fill={part.couleur} />
					{/if}
				{/each}
			</svg>
			<ul>
				{#each parts as part (part.libelle)}
					<li>
						<span class="pastille" style="background: {part.couleur}"></span>
						{part.libelle} : <strong>{part.nombre}</strong> ({pourcentage(part.nombre)} %)
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</section>

<style>
	.camembert {
		border: 3px solid var(--bord);
		box-shadow: var(--ombre);
		background: var(--surface);
		padding: 1rem;
		min-width: 16rem;
		flex: 1 1 16rem;
	}

	.ensemble {
		display: flex;
		gap: 1rem;
		align-items: center;
		flex-wrap: wrap;
	}

	svg {
		width: 9rem;
		height: 9rem;
		flex-shrink: 0;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	li {
		margin: 0.2rem 0;
	}

	.pastille {
		display: inline-block;
		width: 0.8rem;
		height: 0.8rem;
		margin-right: 0.4rem;
		border: 1px solid var(--bord);
	}
</style>
