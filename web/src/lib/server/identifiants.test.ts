import { describe, expect, it } from 'vitest';
import { ErreurIdentifiants, MOT_DE_PASSE_ACTUEL_INCORRECT } from './identifiants.js';
import { ErreurConfirmation } from './jetons-email.js';
import { jetonDuLien, monter, ORIGINE } from './outils-test.js';

const ACTUEL = 'une phrase de passe';
const NOUVEAU = 'un tout nouveau mot de passe';

describe('Identifiants : mot de passe', () => {
	it('refuse sans le bon mot de passe actuel, et ne change rien', async () => {
		const { identifiants, comptes, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');

		const refus = identifiants.changerMotDePasse(moi, 'pas le bon du tout', NOUVEAU, undefined);
		await expect(refus).rejects.toMatchObject({ champ: 'motDePasseActuel', message: MOT_DE_PASSE_ACTUEL_INCORRECT });
		expect(await comptes.authentifier('moi@example.com', ACTUEL)).not.toBeNull();
		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).toBeNull();
	});

	it('refuse un nouveau mot de passe trop court', async () => {
		const { identifiants, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		await expect(identifiants.changerMotDePasse(moi, ACTUEL, 'court', undefined)).rejects.toMatchObject({
			champ: 'nouveauMotDePasse'
		});
	});

	it('change le mot de passe et ferme les autres sessions, pas la sienne', async () => {
		const { identifiants, comptes, sessions, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const ici = sessions.ouvrir(moi.id);
		const ailleurs = sessions.ouvrir(moi.id);

		await identifiants.changerMotDePasse(moi, ACTUEL, NOUVEAU, ici.jeton);

		expect(await comptes.authentifier('moi@example.com', NOUVEAU)).not.toBeNull();
		expect(sessions.valider(ici.jeton)).not.toBeNull();
		expect(sessions.valider(ailleurs.jeton)).toBeNull();
	});

	it("révoque les liens de réinitialisation et d'adresse en circulation", async () => {
		const { identifiants, jetons, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		const reinitialisation = jetons.emettre(moi.id, 'moi@example.com', 'reinitialisation');
		const adresse = jetons.emettre(moi.id, 'inconnu@example.com', 'adresse');

		await identifiants.changerMotDePasse(moi, ACTUEL, NOUVEAU, undefined);

		expect(jetons.lire(reinitialisation)).toBeNull();
		expect(jetons.lire(adresse)).toBeNull();
	});
});

describe('Identifiants : adresse', () => {
	it("n'applique la nouvelle adresse qu'au clic sur le lien qu'elle reçoit, et prévient l'ancienne", async () => {
		const { identifiants, comptes, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');

		await identifiants.demanderChangementAdresse(moi, ACTUEL, 'Nouvelle@Example.com', ORIGINE);
		expect(comptes.parId(moi.id)?.email).toBe('moi@example.com');
		const lien = courrier.envoyes.at(-1)!;
		expect(lien.destinataire).toBe('nouvelle@example.com');

		const { nouvelle } = await identifiants.confirmerAdresse(jetonDuLien(lien.texte));
		expect(nouvelle).toBe('nouvelle@example.com');
		expect(comptes.parId(moi.id)?.email).toBe('nouvelle@example.com');
		expect(await comptes.authentifier('nouvelle@example.com', ACTUEL)).not.toBeNull();
		expect(courrier.envoyes.at(-1)).toMatchObject({
			destinataire: 'moi@example.com',
			sujet: 'RSSResume : adresse du compte modifiée'
		});
		// Le lien ne sert qu'une fois.
		await expect(identifiants.confirmerAdresse(jetonDuLien(lien.texte))).rejects.toBeInstanceOf(ErreurConfirmation);
	});

	it('une adresse mal tapée puis corrigée ne garde pas son lien', async () => {
		const { identifiants, comptes, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');

		await identifiants.demanderChangementAdresse(moi, ACTUEL, 'faute@example.com', ORIGINE);
		const fautif = jetonDuLien(courrier.envoyes.at(-1)!.texte);
		await identifiants.demanderChangementAdresse(moi, ACTUEL, 'bonne@example.com', ORIGINE);
		const bon = jetonDuLien(courrier.envoyes.at(-1)!.texte);
		await expect(identifiants.confirmerAdresse(fautif)).rejects.toBeInstanceOf(ErreurConfirmation);

		await identifiants.confirmerAdresse(bon);
		await expect(identifiants.confirmerAdresse(fautif)).rejects.toBeInstanceOf(ErreurConfirmation);
		expect(comptes.parId(moi.id)?.email).toBe('bonne@example.com');
	});

	it('révoque à la confirmation les autres liens de changement du compte', async () => {
		const { identifiants, jetons, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		await identifiants.demanderChangementAdresse(moi, ACTUEL, 'nouvelle@example.com', ORIGINE);
		// Un lien vers une autre adresse, émis par une version antérieure du site.
		const reste = jetons.emettre(moi.id, 'inconnu@example.com', 'adresse');
		await identifiants.confirmerAdresse(jetonDuLien(courrier.envoyes.at(-1)!.texte));
		expect(jetons.lire(reste)).toBeNull();
	});

	it('refuse sans le bon mot de passe, et sans rien envoyer', async () => {
		const { identifiants, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		await expect(
			identifiants.demanderChangementAdresse(moi, 'pas le bon du tout', 'nouvelle@example.com', ORIGINE)
		).rejects.toMatchObject({ champ: 'motDePasseActuel' });
		expect(courrier.envoyes).toEqual([]);
	});

	it("refuse une adresse invalide, identique ou déjà prise par un autre compte", async () => {
		const { identifiants, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		await creerConfirme('autre@example.com', 'autre');
		for (const adresse of ['pas une adresse', 'MOI@example.com', 'autre@example.com']) {
			const refus = identifiants.demanderChangementAdresse(moi, ACTUEL, adresse, ORIGINE);
			await expect(refus).rejects.toBeInstanceOf(ErreurIdentifiants);
			await expect(refus).rejects.toMatchObject({ champ: 'email' });
		}
	});

	it("refuse la confirmation quand l'adresse a été prise entre-temps", async () => {
		const { identifiants, comptes, courrier, creerConfirme } = monter();
		const moi = await creerConfirme('moi@example.com', 'moi');
		await identifiants.demanderChangementAdresse(moi, ACTUEL, 'nouvelle@example.com', ORIGINE);
		await creerConfirme('nouvelle@example.com', 'rapide');

		await expect(identifiants.confirmerAdresse(jetonDuLien(courrier.envoyes.at(-1)!.texte))).rejects.toBeInstanceOf(
			ErreurConfirmation
		);
		expect(comptes.parId(moi.id)?.email).toBe('moi@example.com');
	});
});
