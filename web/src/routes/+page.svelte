<section class="accueil">
	<p class="eyebrow">Votre veille professionnelle</p>
	<h1>Votre veille, résumée et lue à voix haute</h1>

	<div class="carte presentation">
		<p class="accroche">
			RSSResume lit les articles de la veille, garde ceux qui comptent pour vous,
			les résume et en fait un épisode audio envoyé par email.
		</p>
		<p>
			Ce que « compter pour vous » veut dire, c'est votre <strong>profil</strong> qui le décide :
			votre métier, vos axes de veille et les composants que vous exploitez.
		</p>
		<div class="actions">
			<a class="bouton" href="/inscription">Créer un compte</a>
			<a class="bouton bouton-secondaire" href="/connexion">Se connecter</a>
		</div>
	</div>
</section>

<style>
	.accueil {
		padding-top: 1.5rem;
	}

	.eyebrow {
		display: inline-block;
		margin: 0 0 1.25rem;
		padding: 0.35rem 0.65rem;
		background: var(--texte);
		color: var(--accent);
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.presentation {
		max-width: 48rem;
	}

	.accroche {
		font-family: Impact, 'Arial Black', Arial, sans-serif;
		font-size: clamp(1.35rem, 3vw, 2.1rem);
		line-height: 1.12;
		text-transform: uppercase;
		margin-top: 0;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-top: 1.5rem;
	}

	.bouton-secondaire {
		background: var(--surface);
		color: var(--texte);
	}

	@media (max-width: 520px) {
		.accueil {
			padding-top: 0.25rem;
		}

		.actions {
			display: grid;
		}

		.bouton {
			width: 100%;
			text-align: center;
		}
	}
</style>
