import unittest
from types import SimpleNamespace

from app import distance_band, reflection_queries


class MultiStageSearchTests(unittest.TestCase):
    def test_distance_band_keeps_all_close_candidates_and_nearest(self):
        candidates = [
            (0.50, "a"),
            (0.61, "b"),
            (0.64, "c"),
            (0.82, "d"),
        ]
        selected = distance_band(candidates, delta=0.15, hard_cap=25)
        self.assertEqual([item_id for _, item_id in selected], ["a", "b", "c"])

    def test_distance_band_is_bounded_even_when_query_is_broad(self):
        candidates = [(0.50 + i * 0.001, str(i)) for i in range(100)]
        selected = distance_band(candidates, delta=0.2, hard_cap=7)
        self.assertEqual(len(selected), 7)
        self.assertEqual(selected[0], (0.50, "0"))

    def test_reflection_queries_are_new_bounded_and_preserve_original(self):
        original = "future energy"
        rows = [
            SimpleNamespace(title="Energy systems and durable futures", body="energy systems future durable"),
            SimpleNamespace(title="Attention and power", body="attention energy"),
        ]
        queries = reflection_queries(original, rows, limit=3)
        self.assertLessEqual(len(queries), 3)
        self.assertTrue(all(original in query for query in queries))
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all(query != original for query in queries))
    def test_crypto_question_gets_evidence_weighted_definition(self):
        from app import build_search_answer
        answer = build_search_answer(
            "what is crypto?",
            [{"id": "a", "title": "crypto note", "day": "2025-05-22", "source": "archive", "distance": 0.5, "body_excerpt": "Crypto is a layer for real value creation, but speculation creates a noisy price signal and distrust."}],
            "multi-stage-chroma",
            0,
            {"stage_count": 6, "stage_candidate_total": 300, "reflection_count": 5, "lexical_count": 0},
        )
        self.assertIn("cryptoeconomic coordination layer", answer["text"])
        self.assertIn("speculation", answer["text"])
        self.assertEqual(answer["synthesis"]["search_effort"]["time_x_effort_index"], 0)
    def test_ai_question_gets_evidence_weighted_definition(self):
        from app import build_search_answer
        answer = build_search_answer(
            "what is AI?",
            [{"id": "a", "title": "AI note", "day": "2025-02-16", "source": "archive", "distance": 0.42, "body_excerpt": "AI is a function that transforms inputs into more valuable outputs. It is a tool shaped by human coordination, not an independent entity."}],
            "multi-stage-chroma",
            0,
            {"stage_count": 6, "stage_candidate_total": 300, "reflection_count": 5, "lexical_count": 0},
        )
        self.assertIn("transforms inputs into more valuable outputs", answer["text"])
        self.assertIn("human coordination", answer["text"])
        self.assertIsNotNone(answer["synthesis"])
    def test_quai_question_gets_calibrated_entity_synthesis(self):
        from app import build_search_answer
        answer = build_search_answer(
            "why quai?",
            [{"id": "a", "title": "Quai note", "day": "2026-07-24", "source": "archive", "distance": 0.9, "body_excerpt": "Quai is energy efficient and low energy. The network rewards tips, staking, referrals, and distributed sensor receipts."}],
            "multi-stage-chroma+fts",
            0,
            {"stage_count": 6, "stage_candidate_total": 300, "reflection_count": 5, "lexical_count": 13},
        )
        self.assertIn("energy efficiency and lower variance", answer["text"])
        self.assertIn("incentive layer", answer["text"])
        self.assertIn("does not establish", answer["text"])
        self.assertIsNotNone(answer["synthesis"])

    def test_compressed_answer_is_one_shareable_sentence(self):
        from app import build_search_answer
        answer = build_search_answer(
            "crypto",
            [{"title": "@leo_guinan · 2021-05-27 · tweet 123", "day": "2021-05-27", "source": "Leo Twitter archive"}],
            "multi-stage-chroma",
            0,
            {"stage_count": 6},
        )
        self.assertEqual(answer["text"], "1 document over 2021-05-27 reveal a collective answer of crypto is most strongly connected to @leo_guinan · 2021-05-27 · tweet 123.")
        self.assertEqual(answer["text"].count("."), 1)


if __name__ == "__main__":
    unittest.main()
