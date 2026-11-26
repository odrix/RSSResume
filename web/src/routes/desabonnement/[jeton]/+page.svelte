<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Se désabonner, RSSResume</title>
</svelte:head>

<h1>Se désabonner</h1>

{#if form && 'desabonne' in form}
	<p class="message succes" role="status">
		Le résumé du profil « {form.desabonne} » ne sera plus envoyé par email.
	</p>
	<p>
		Pour le recevoir de nouveau, ajoutez une adresse dans <a href="/profil">votre profil</a>.
	</p>
{:else if form && 'message' in form}
	<p class="message erreur" role="alert">{form.message}</p>
	<p><a href="/profil">Gérer les destinataires depuis votre profil</a></p>
{:else if data.invalide}
	<p class="message erreur" role="alert">{data.invalide}</p>
	<p><a href="/profil">Gérer les destinataires depuis votre profil</a></p>
{:else if data.demande}
	<form method="POST" class="formulaire carte">
		<p>
			Le résumé du profil <strong>« {data.demande.username} »</strong> ne sera plus envoyé à
			{data.demande.destinataires === 1
				? 'son destinataire'
				: `ses ${data.demande.destinataires} destinataires`}.
		</p>
		<button type="submit">Me désabonner</button>
	</form>
{/if}
