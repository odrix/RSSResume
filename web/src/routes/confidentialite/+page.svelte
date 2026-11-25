<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>Confidentialité — RSSResume</title>
</svelte:head>

<h1>Confidentialité</h1>

<p>
	RSSResume lit chaque jour des flux d'actualité, retient les articles qui correspondent à votre
	profil et vous envoie un résumé par email, à lire et à écouter. Cette page dit ce que le service
	garde de vous, pourquoi, combien de temps, et à qui il le confie.
</p>

<h2>Les données conservées</h2>
<ul>
	<li>
		<strong>Votre compte</strong> : adresse email, nom d'utilisateur, mot de passe — dont seule une
		empreinte Argon2id est gardée, jamais le mot de passe lui-même —, dates de création, de
		confirmation et de dernière connexion, et les jours où vous avez consulté vos résumés.
	</li>
	<li>
		<strong>Votre profil</strong> : le texte qui décrit votre veille, votre prénom s'il est renseigné,
		les catégories et rubriques suivies, le régime de sécurité et la <strong>stack</strong> surveillée
		(les logiciels dont vous voulez suivre les failles), et les adresses qui reçoivent le résumé.
	</li>
	<li>
		<strong>Vos journées</strong> : pour chaque jour, les articles retenus, leurs notes et résumés,
		l'email envoyé et son audio, et l'avis que vous avez éventuellement donné sur le résumé.
	</li>
	<li>
		<strong>Techniques</strong> : un cookie de session, posé seulement quand vous vous connectez et
		nécessaire à la connexion. Aucun cookie de mesure d'audience ni de publicité.
	</li>
</ul>

<h2>Finalité</h2>
<p>
	Ces données servent uniquement à vous connecter, à choisir et résumer les articles qui vous
	concernent, à vous les envoyer, et à améliorer la sélection d'après vos avis. Elles ne sont ni
	vendues, ni cédées, ni utilisées pour de la publicité.
</p>

<h2>Durée de conservation</h2>
<ul>
	<li>Un compte jamais confirmé est supprimé au bout de sept jours.</li>
	<li>Une session expire après trente jours sans visite.</li>
	<li>
		Les liens envoyés par email expirent : une heure pour un nouveau mot de passe, vingt-quatre heures
		pour confirmer une adresse.
	</li>
	<li>Le compte, le profil et les journées sont gardés tant que le compte existe.</li>
</ul>

<h2>Sous-traitants</h2>
<ul>
	<li>
		<strong>Le fournisseur de modèles de langage</strong> configuré pour le service (OpenAI ou Mistral) :
		il reçoit le texte des articles et celui de votre profil, pour noter les articles, les résumer
		et produire l'audio. Il ne reçoit ni votre adresse email ni votre mot de passe.
	</li>
	<li>
		<strong>Resend</strong> : il achemine les emails du service — confirmations, nouveaux mots de passe et
		résumé quotidien. Il reçoit votre adresse et le contenu de ces emails.
	</li>
</ul>

<h2>Vos droits, et la suppression du compte</h2>
<p>
	Vous pouvez à tout moment lire et corriger votre profil dans « Mon profil », et changer votre
	adresse ou votre mot de passe dans « Mon compte ». Pour ne plus rien recevoir, videz les adresses de
	réception de votre profil.
</p>
<p>
	<strong>La suppression de votre compte</strong> — et avec lui de votre profil et de vos journées —, ou
	une copie de vos données, se demande au contact ci-dessous, depuis l'adresse de votre compte.
</p>

<h2>Contact</h2>
{#if data.contact}
	<p><a href="mailto:{data.contact}">{data.contact}</a></p>
{:else}
	<p>L'administrateur de ce site n'a pas encore publié d'adresse de contact.</p>
{/if}
