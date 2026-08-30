"""Le réessai des appels réseau, jugé sans réseau.

`http.retry` ne reçoit qu'un appel à tenter : une doublure qui échoue N fois avant de
réussir suffit à le décrire entièrement. L'attente est injectée, donc aucun test ne dort.
"""

import io
import json
import logging
import tempfile
import unittest
import urllib.error
from unittest import mock

from rssresume.external.freshrss import FreshRSSClient
from rssresume.llm.openai import OpenAIProvider
from rssresume.tools import http
from tests.support import make_config


# Les reprises sont tracées là où elles comptent, pas déversées dans la sortie des tests.
logging.getLogger("rssresume.tools.http").setLevel(logging.CRITICAL)


#: Les `HTTPError` fabriquées ici tiennent un flux ouvert et se plaignent en le perdant.
_ERREURS = []


def http_error(code, headers=None):
    erreur = urllib.error.HTTPError(
        "https://api.example/v1/chat", code, "erreur", headers or {}, io.BytesIO(b"corps")
    )
    _ERREURS.append(erreur)
    return erreur


def tearDownModule():
    for erreur in _ERREURS:
        erreur.close()
    _ERREURS.clear()


class Doublure:
    """Un appel qui échoue `echecs` fois, puis réussit. Compte ses tentatives."""

    def __init__(self, echecs, exception=None, valeur="ok"):
        self.echecs = echecs
        self.exception = exception or http_error(503)
        self.valeur = valeur
        self.tentatives = 0

    def __call__(self):
        self.tentatives += 1
        if self.tentatives <= self.echecs:
            raise self.exception
        return self.valeur


class RetryTests(unittest.TestCase):
    @staticmethod
    def _retry(operation, **kwargs):
        """Rejoue sans jamais dormir ; rend (résultat, délais demandés)."""
        delais = []
        return http.retry(operation, "test", sleep=delais.append, **kwargs), delais

    def test_a_transient_failure_is_replayed_until_it_succeeds(self):
        appel = Doublure(echecs=2)

        resultat, delais = self._retry(appel)

        self.assertEqual("ok", resultat)
        self.assertEqual(3, appel.tentatives)
        self.assertEqual(2, len(delais))

    def test_the_delay_grows_between_attempts(self):
        """Backoff exponentiel : la deuxième attente est plus longue que la première."""
        _, delais = self._retry(Doublure(echecs=2))

        self.assertLess(delais[0], delais[1])
        self.assertLessEqual(delais[-1], http.MAX_DELAY)

    def test_an_exhausted_retry_raises_the_original_error(self):
        """L'appelant traduit l'erreur de transport : elle doit lui parvenir intacte."""
        appel = Doublure(echecs=5)

        with self.assertRaises(urllib.error.HTTPError) as leve:
            self._retry(appel)

        self.assertEqual(503, leve.exception.code)
        self.assertEqual(http.ATTEMPTS, appel.tentatives)

    def test_a_client_error_is_never_replayed(self):
        """Un 404 ou un 401 rendra la même réponse : le rejouer ne fait que perdre du temps."""
        for code in (400, 401, 403, 404, 422):
            appel = Doublure(echecs=5, exception=http_error(code))

            with self.assertRaises(urllib.error.HTTPError):
                self._retry(appel)

            self.assertEqual(1, appel.tentatives, code)

    def test_every_retryable_status_is_replayed(self):
        for code in sorted(http.RETRYABLE_STATUS):
            appel = Doublure(echecs=1, exception=http_error(code))

            resultat, _ = self._retry(appel)

            self.assertEqual("ok", resultat, code)
            self.assertEqual(2, appel.tentatives, code)

    def test_a_connection_error_is_replayed_too(self):
        """Une coupure réseau n'a pas de code : elle passe par `URLError`."""
        appel = Doublure(echecs=1, exception=urllib.error.URLError("connexion refusée"))

        resultat, _ = self._retry(appel)

        self.assertEqual("ok", resultat)
        self.assertEqual(2, appel.tentatives)

    def test_a_timeout_is_replayed_too(self):
        appel = Doublure(echecs=1, exception=TimeoutError("lecture trop longue"))

        resultat, _ = self._retry(appel)

        self.assertEqual("ok", resultat)

    def test_retry_after_in_seconds_wins_over_the_backoff(self):
        """Le serveur connaît la fenêtre de son quota mieux que notre exponentielle."""
        appel = Doublure(echecs=1, exception=http_error(429, {"Retry-After": "7"}))

        _, delais = self._retry(appel)

        self.assertEqual([7.0], delais)

    def test_retry_after_as_a_date_is_understood(self):
        entete = {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
        appel = Doublure(echecs=1, exception=http_error(429, entete))

        _, delais = self._retry(appel)

        # Une date lointaine est ramenée au plafond : on n'attend pas jusqu'en 2099.
        self.assertEqual([http.MAX_DELAY], delais)

    def test_an_unreadable_retry_after_falls_back_on_the_backoff(self):
        appel = Doublure(echecs=1, exception=http_error(429, {"Retry-After": "bientôt"}))

        _, delais = self._retry(appel)

        self.assertEqual(1, len(delais))
        self.assertGreater(delais[0], 0)

    def test_a_call_that_succeeds_at_once_never_sleeps(self):
        appel = Doublure(echecs=0)

        resultat, delais = self._retry(appel)

        self.assertEqual("ok", resultat)
        self.assertEqual([], delais)


class WiringTests(unittest.TestCase):
    """Les deux clients réseau du projet passent bien par le réessai."""

    @staticmethod
    def _urlopen(reponses):
        """Un `urlopen` qui rend les réponses données, exception comprise."""
        restantes = list(reponses)

        def _ouvrir(request, *args, **kwargs):
            reponse = restantes.pop(0)
            if isinstance(reponse, Exception):
                raise reponse
            return mock.MagicMock(
                __enter__=mock.Mock(return_value=mock.Mock(read=mock.Mock(return_value=reponse))),
                __exit__=mock.Mock(return_value=False),
            )

        return _ouvrir

    def test_the_provider_replays_a_failed_completion(self):
        """Un 502 du fournisseur ne doit plus coûter la catégorie en cours."""
        corps = json.dumps(
            {"choices": [{"message": {"content": "texte"}, "finish_reason": "stop"}]}
        ).encode()
        provider = OpenAIProvider(_settings())

        with mock.patch("time.sleep"):
            with mock.patch("urllib.request.urlopen", self._urlopen([http_error(502), corps])):
                self.assertEqual(corps, provider._post("/chat/completions", {}, "digest"))

    def test_freshrss_replays_a_failed_request(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FreshRSSClient(make_config(tmpdir))
            with mock.patch("time.sleep"):
                with mock.patch(
                    "urllib.request.urlopen", self._urlopen([http_error(503), b"corps"])
                ):
                    self.assertEqual(b"corps", client._request("https://example.com/x"))

    def test_freshrss_gives_up_on_a_client_error(self):
        """Un 401 de FreshRSS est une erreur de configuration : la rejouer n'y changera rien."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FreshRSSClient(make_config(tmpdir))
            with mock.patch("time.sleep") as dormir:
                with mock.patch("urllib.request.urlopen", self._urlopen([http_error(401)])):
                    with self.assertRaises(RuntimeError) as leve:
                        client._request("https://example.com/x")

            self.assertIn("401", str(leve.exception))
            dormir.assert_not_called()


def _settings():
    """Les réglages minimaux d'un fournisseur, pour n'observer que le transport."""
    from rssresume.llm.providers import Call, Settings, Voice

    return Settings(
        name="openai",
        label="OpenAI",
        base_url="https://api.example/v1",
        api_key="key",
        calls={"digest": Call("digest", "gpt-4o-mini")},
        voice=Voice(model="tts", voice="alloy"),
        prices={},
    )


if __name__ == "__main__":
    unittest.main()
