import unittest

from sniper_ai.scoring import score_listing


class ScoringTests(unittest.TestCase):
    def test_discount_improves_score(self):
        result = score_listing(70000, 100000, condition="new", seller_verified=True, has_delivery=True)
        self.assertEqual(result.discount_percent, 30.0)
        self.assertGreaterEqual(result.score, 70)

    def test_missing_comparison_is_not_treated_as_deal(self):
        result = score_listing(50000, None)
        self.assertIsNone(result.discount_percent)
        self.assertIn("Недостаточно данных для сравнения цены", result.reasons)

    def test_suspicious_text_increases_risk(self):
        result = score_listing(50000, 60000, suspicious_text=True)
        self.assertEqual(result.risk_level, "high")

    def test_score_is_bounded(self):
        result = score_listing(1, 1000000, condition="new", seller_verified=True, has_delivery=True)
        self.assertLessEqual(result.score, 100)
        self.assertGreaterEqual(result.score, 0)


if __name__ == "__main__":
    unittest.main()
