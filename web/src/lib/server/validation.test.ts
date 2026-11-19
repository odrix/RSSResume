import { describe, expect, it } from 'vitest';
import { erreurEmail, erreurMotDePasse, erreurUsername, normaliserEmail } from './validation.js';

describe('username', () => {
	it.each(['ab', 'adrien', 'a-b_c', '0x', 'a'.repeat(32)])('accepte %s', (username) => {
		expect(erreurUsername(username)).toBeNull();
	});

	it.each(['a', '', '-adrien', '_adrien', 'Adrien', 'adr ien', 'adrien!', 'é', 'a'.repeat(33), '../x'])(
		'refuse %s',
		(username) => {
			expect(erreurUsername(username)).toMatch(/2 à 32 caractères/);
		}
	);
});

describe('mot de passe', () => {
	it('exige douze caractères', () => {
		expect(erreurMotDePasse('a'.repeat(11))).toMatch(/au moins 12/);
		expect(erreurMotDePasse('a'.repeat(12))).toBeNull();
	});

	it('compte les caractères et non les unités UTF-16', () => {
		// Six emojis font douze unités UTF-16 mais six caractères.
		expect(erreurMotDePasse('🔑'.repeat(6))).toMatch(/au moins 12/);
		expect(erreurMotDePasse('🔑'.repeat(12))).toBeNull();
	});

	it('plafonne la longueur', () => {
		expect(erreurMotDePasse('a'.repeat(257))).toMatch(/au plus 256/);
	});
});

describe('email', () => {
	it('accepte une adresse ordinaire et refuse le reste', () => {
		expect(erreurEmail('moi@example.com')).toBeNull();
		expect(erreurEmail('moi@example')).not.toBeNull();
		expect(erreurEmail('moi example.com')).not.toBeNull();
		expect(erreurEmail('')).not.toBeNull();
	});

	it('normalise la casse et les espaces', () => {
		expect(normaliserEmail('  Moi@Example.COM ')).toBe('moi@example.com');
	});
});
