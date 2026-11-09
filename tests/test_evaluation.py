import json
from pathlib import Path
from unittest import TestCase

from evaluation.run_checks import evaluate, word_error_rate


class EvaluationTests(TestCase):
    def test_synthetic_grounding_cases(self):
        cases = json.loads(
            (Path(__file__).resolve().parents[1] / "evaluation/cases.json").read_text()
        )
        result = evaluate(cases)
        self.assertEqual(result["passed"], result["cases"])

    def test_word_error_rate_counts_insertions_deletions_and_substitutions(self):
        self.assertEqual(word_error_rate("one two three", "one two three")["wer"], 0)
        self.assertEqual(word_error_rate("one two three", "one four")["word_errors"], 2)
        self.assertEqual(word_error_rate("One, two.", "one two extra")["wer"], 0.5)
        with self.assertRaises(ValueError):
            word_error_rate("", "anything")
