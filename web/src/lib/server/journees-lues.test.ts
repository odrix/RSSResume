import { beforeEach, describe, expect, it } from 'vitest';
import { ouvrirBase } from './base.js';
import type { Utilisateur } from './comptes.js';
import { EMAIL_ADMIN, monter } from './outils-test.js';

const JOUR = '2026-11-22';
const VEILLE = '2026-11-21';

describe('JourneesLues', () => {
	let env: ReturnType<typeof monter>;
	let moi: Utilisateur;
	let autre: Utilisateur;
	let admin: Utilisateur;

	function lignes() {
		return env.base.prepare('SELECT compte_id, date, origine, lue_le FROM journees_lues ORDER BY date').all();
	}

	beforeEach(async () => {
		env = monter(() => Date.parse('2026-11-26T08:00:00Z'));
		moi = await env.creerConfirme('moi@example.com', 'moi');
		autre = await env.creerConfirme('autre@example.com', 'autre');
		admin = await env.creerConfirme(EMAIL_ADMIN, 'chef');
	});

	it('la base migrée a sa table', () => {
		const base = ouvrirBase(':memory:');
		expect(
			base.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'journees_lues'").get()
		).toEqual({ name: 'journees_lues' });
	});

	it('rend lue la journée marquée, et elle seule', () => {
		expect(env.journeesLues.marquer(moi, 'moi', JOUR, 'pages')).toBe(true);

		expect(env.journeesLues.lues(moi, 'moi')).toEqual(new Set([JOUR]));
		expect(lignes()).toEqual([{ compte_id: moi.id, date: JOUR, origine: 'pages', lue_le: '2026-11-26T08:00:00.000Z' }]);
	});

	it("lire puis écouter ne compte qu'une fois, et la première origine reste", () => {
		env.journeesLues.marquer(moi, 'moi', JOUR, 'pages');
		expect(env.journeesLues.marquer(moi, 'moi', JOUR, 'audio')).toBe(true);

		expect(lignes()).toEqual([expect.objectContaining({ date: JOUR, origine: 'pages' })]);
	});

	it("n'écrit rien sur la journée d'un autre, administrateur compris", () => {
		expect(env.journeesLues.marquer(moi, 'autre', JOUR, 'pages')).toBe(false);
		expect(env.journeesLues.marquer(admin, 'moi', JOUR, 'audio')).toBe(false);

		expect(lignes()).toEqual([]);
	});

	it('refuse un username ou une date mal formés', () => {
		expect(env.journeesLues.marquer(moi, 'moi', '../x', 'pages')).toBe(false);
		expect(env.journeesLues.marquer(moi, 'moi', '20261122', 'pages')).toBe(false);
		expect(lignes()).toEqual([]);
	});

	it("ne montre à personne les lectures d'un autre", () => {
		env.journeesLues.marquer(moi, 'moi', JOUR, 'pages');
		env.journeesLues.marquer(autre, 'autre', VEILLE, 'audio');

		expect(env.journeesLues.lues(autre, 'autre')).toEqual(new Set([VEILLE]));
		expect(env.journeesLues.lues(moi, 'moi')).toEqual(new Set([JOUR]));
		expect(env.journeesLues.lues(admin, 'moi')).toEqual(new Set());
		expect(env.journeesLues.lues(autre, 'moi')).toEqual(new Set());
	});
});
