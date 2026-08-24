"""Robustesse du scoring face aux réponses du modèle : mapping des notes sur les articles."""

import json
import logging
import unittest
from unittest import mock

from rssresume import processing
from rssresume.processing import ProcessingError, score_articles

# Les identifiants FreshRSS réels : longs, et recopiés de travers par le modèle.
ITEM_1 = "tag:google.com,2005:reader/item/000659ce0338ac4f"
ITEM_2 = "tag:google.com,2005:reader/item/000659ce0338ac50"

CREDENTIALS = ("https://api.example/v1", "key")

# Les avertissements de réalignement sont vérifiés là où ils comptent, pas affichés partout.
logging.getLogger("rssresume.processing").setLevel(logging.CRITICAL)


def article(item_id, title="Titre"):
    return {"id": item_id, "title": title, "summary": "Résumé court."}


def note(id_renvoye, score, thematique="cyber", angle="a"):
    return {"id": id_renvoye, "score": score, "thematique": thematique, "angle": angle}


def _json(notes):
    return json.dumps({"resultats": notes}, ensure_ascii=False)


class ScoringMappingTests(unittest.TestCase):
    def _score(self, articles, notes_renvoyees):
        with mock.patch("rssresume.processing._call", return_value=_json(notes_renvoyees)) as call:
            scored = score_articles(articles, credentials=CREDENTIALS)
        return scored, call

    def test_the_model_never_receives_the_freshrss_identifiers(self):
        """C'est la cause de l'échec d'origine : des ids longs mal recopiés."""
        _, call = self._score([article(ITEM_1), article(ITEM_2)], [note("1", 9), note("2", 3)])

        envoye = call.call_args.args[1]
        self.assertNotIn(ITEM_1, envoye)
        self.assertIn('"id": "1"', envoye)
        self.assertIn('"id": "2"', envoye)

    def test_numbered_answers_map_back_to_the_original_identifiers(self):
        scored, _ = self._score([article(ITEM_1), article(ITEM_2)], [note("1", 9), note("2", 3)])

        self.assertEqual([ITEM_1, ITEM_2], [item["id"] for item in scored])
        self.assertEqual([9, 3], [item["score"] for item in scored])

    def test_answers_out_of_order_follow_their_number(self):
        scored, _ = self._score([article(ITEM_1), article(ITEM_2)], [note("2", 3), note("1", 9)])

        self.assertEqual({ITEM_1: 9, ITEM_2: 3}, {item["id"]: item["score"] for item in scored})

    def test_unreadable_numbers_fall_back_on_the_answer_order(self):
        """Le cas qui faisait échouer tout le lot : un id que le modèle a réécrit."""
        with self.assertLogs("rssresume.processing", level="WARNING") as journal:
            scored, _ = self._score(
                [article(ITEM_1), article(ITEM_2)],
                [note(ITEM_1[:-1], 9), note("article 2", 3)],
            )

        self.assertEqual([ITEM_1, ITEM_2], [item["id"] for item in scored])
        self.assertEqual([9, 3], [item["score"] for item in scored])
        # Le rattrapage est silencieux pour l'utilisateur, mais tracé dans les logs.
        self.assertIn("rattachée(s) par ordre", journal.output[-1])

    def test_a_duplicated_number_does_not_overwrite_its_neighbour(self):
        scored, _ = self._score(
            [article(ITEM_1), article(ITEM_2)], [note("1", 9), note("1", 3)]
        )

        # La deuxième note ne peut plus prendre la place 1 : elle tombe sur la seule libre.
        self.assertEqual([ITEM_1, ITEM_2], [item["id"] for item in scored])
        self.assertEqual([9, 3], [item["score"] for item in scored])

    def test_a_missing_note_still_stops_the_run(self):
        """Un lot tronqué reste une erreur : la sélection ne doit pas rétrécir en silence."""
        with mock.patch("rssresume.processing._call", return_value=_json([note("1", 9)])):
            with self.assertRaises(ProcessingError):
                score_articles([article(ITEM_1), article(ITEM_2)], credentials=CREDENTIALS)

    def test_a_non_object_entry_yields_a_zero_score_without_shifting_the_others(self):
        scored, _ = self._score([article(ITEM_1), article(ITEM_2)], ["n'importe quoi", note("2", 3)])

        self.assertEqual({ITEM_1: 0, ITEM_2: 3}, {item["id"]: item["score"] for item in scored})

    def test_batches_are_numbered_from_one_each_time(self):
        """Chaque lot repart à 1 : le numéro est local à l'appel, pas global au lot d'articles."""
        articles = [article(f"item-{i}") for i in range(processing.SCORING_BATCH_SIZE + 2)]
        appels = []

        def _call(system, user, profile, credentials=None):
            appels.append(user)
            envoyes = user.count('"titre"')
            return _json([note(str(rang), 5) for rang in range(1, envoyes + 1)])

        with mock.patch("rssresume.processing._call", side_effect=_call):
            scored = score_articles(articles, credentials=CREDENTIALS)

        self.assertEqual(2, len(appels))
        self.assertIn('"id": "1"', appels[1])
        self.assertEqual([a["id"] for a in articles], [item["id"] for item in scored])



if __name__ == "__main__":
    unittest.main()
