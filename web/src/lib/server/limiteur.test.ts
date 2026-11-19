import { expect, it } from 'vitest';
import { LimiteurTentatives } from './limiteur.js';

it('bloque au-delà du maximum, puis relâche quand la fenêtre a glissé', () => {
	let t = 0;
	const limiteur = new LimiteurTentatives(3, 60_000, () => t);
	for (let i = 0; i < 3; i++) {
		expect(limiteur.autorise('moi@example.com')).toBe(true);
		limiteur.noter('moi@example.com');
		t += 1_000;
	}
	expect(limiteur.autorise('moi@example.com')).toBe(false);
	expect(limiteur.attenteSecondes('moi@example.com')).toBe(57);
	expect(limiteur.autorise('autre@example.com')).toBe(true);

	t = 60_001;
	expect(limiteur.autorise('moi@example.com')).toBe(true);
});

it('oublie une clé après un succès', () => {
	const limiteur = new LimiteurTentatives(1, 60_000);
	limiteur.noter('x');
	expect(limiteur.autorise('x')).toBe(false);
	limiteur.oublier('x');
	expect(limiteur.autorise('x')).toBe(true);
});
