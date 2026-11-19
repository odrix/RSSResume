import type { Utilisateur } from '#lib/server/comptes.js';

declare global {
	namespace App {
		interface Locals {
			/** La personne connectée, posée par `hooks.server.ts` ; `null` sinon. */
			utilisateur: Utilisateur | null;
		}
	}
}

export {};
