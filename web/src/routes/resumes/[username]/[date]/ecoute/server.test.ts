import { isHttpError } from '@sveltejs/kit';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Utilisateur } from '#lib/server/comptes.js';
import { ConsultationResumes } from '#lib/server/consultation.js';
import { EMAIL_ADMIN, monter } from '#lib/server/outils-test.js';

/* Le contexte réel lit l'environnement et ouvre la base : la route reçoit à la place celui
 * des tests, monté sur la fausse API. */
const etat = vi.hoisted(() => ({ env: null as unknown }));
vi.mock('#lib/server/contexte.js', () => ({ contexte: () => etat.env }));

const { POST } = await import('./+server.js');

const JOUR = '2026-11-22';

type Env = ReturnType<typeof monter>;

function evenement(utilisateur: Utilisateur | null, username = 'bea', date = JOUR) {
	return {
		params: { username, date },
		locals: { utilisateur },
		request: new Request(`https://site.test/resumes/${username}/${date}/ecoute`, { method: 'POST' })
	} as never;
}

async function leve(promesse: unknown): Promise<unknown> {
	try {
		await promesse;
	} catch (lancee) {
		return lancee;
	}
	throw new Error("rien n'a été levé");
}

describe('POST /resumes/[username]/[date]/ecoute', () => {
	let env: Env;
	let bea: Utilisateur;
	let admin: Utilisateur;

	function lignes() {
		return env.base.prepare('SELECT compte_id, date, origine FROM journees_lues').all();
	}

	beforeEach(async () => {
		env = monter();
		await env.api.creerProfil('bea', { profil: 'Veille', stack: [], email: [], prenom: '', securite: 'exploitant' });
		env.fausseApi.ajouterContenu('bea', JOUR, {});
		bea = await env.creerConfirme('bea@example.com', 'bea');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
		etat.env = { ...env, consultation: new ConsultationResumes(env.api) };
	});

	it('marque la journée écoutée, une seule fois même signalée deux fois', async () => {
		const reponse = await POST(evenement(bea));
		expect(reponse.status).toBe(204);
		expect(env.journeesLues.lues(bea, 'bea')).toEqual(new Set([JOUR]));

		expect((await POST(evenement(bea))).status).toBe(204);
		expect(lignes()).toEqual([{ compte_id: bea.id, date: JOUR, origine: 'audio' }]);
	});

	it("ne compte pas l'écoute en plus d'une lecture des pages", async () => {
		env.journeesLues.marquer(bea, 'bea', JOUR, 'pages');

		expect((await POST(evenement(bea))).status).toBe(204);
		expect(lignes()).toEqual([{ compte_id: bea.id, date: JOUR, origine: 'pages' }]);
	});

	it("rend 404 pour une journée qui n'existe pas", async () => {
		expect(isHttpError(await leve(POST(evenement(bea, 'bea', '2026-11-21'))), 404)).toBe(true);
		expect(lignes()).toEqual([]);
	});

	it('rend 401 sans session', async () => {
		expect(isHttpError(await leve(POST(evenement(null))), 401)).toBe(true);
		expect(lignes()).toEqual([]);
	});

	it("rend 404 à un admin sur la journée d'un autre, sans rien écrire", async () => {
		expect(isHttpError(await leve(POST(evenement(admin))), 404)).toBe(true);
		expect(lignes()).toEqual([]);
	});
});
