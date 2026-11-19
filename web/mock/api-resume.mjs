/**
 * La fausse API de résumé, servie en HTTP pour développer le site sans l'appli Python.
 *
 *     npm run mock          # http://localhost:8080, jeton « dev »
 *
 * Chaque profil créé reçoit deux journées d'audio silencieux, pour essayer le lecteur.
 * Tout est en mémoire : un redémarrage vide les profils, pas les comptes du site.
 */

import { createServer } from 'node:http';
import { Readable } from 'node:stream';
import { FausseApi } from './faux-api.js';

const port = Number(process.env.MOCK_PORT ?? 8080);
const jeton = process.env.RSSRESUME_API_TOKEN || 'dev';
const api = new FausseApi(jeton);
api.journeesDeDemo = true;

createServer(async (req, res) => {
	const corps = req.method === 'GET' || req.method === 'HEAD' ? undefined : Readable.toWeb(req);
	const requete = new Request(`http://localhost:${port}${req.url}`, {
		method: req.method,
		headers: /** @type {Record<string, string>} */ (req.headers),
		body: /** @type {any} */ (corps),
		duplex: 'half'
	});
	const reponse = await api.traiter(requete);
	console.log(`${req.method} ${req.url} ${req.headers.range ?? ''} → ${reponse.status}`);
	res.writeHead(reponse.status, Object.fromEntries(reponse.headers));
	if (reponse.body) Readable.fromWeb(/** @type {any} */ (reponse.body)).pipe(res);
	else res.end();
}).listen(port, () => {
	console.log(`Fausse API de résumé sur http://localhost:${port} (jeton « ${jeton} »)`);
});
