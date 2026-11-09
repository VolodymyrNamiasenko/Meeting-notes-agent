"""Reproducible synthetic grounding checks and optional local audio WER."""

import argparse
import json
import re
from pathlib import Path

from meeting_pipeline import PipelineError, validate_notes


def word_error_rate(reference, actual):
    def words(value):
        return re.findall(r"\w+", value.casefold())

    ref, hypothesis = words(reference), words(actual)
    if not ref:
        raise ValueError("A non-empty reference is required.")
    row = list(range(len(hypothesis) + 1))
    for i, word in enumerate(ref, 1):
        nxt = [i]
        for j, observed in enumerate(hypothesis, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (word != observed)))
        row = nxt
    return {
        "reference_words": len(ref),
        "word_errors": row[-1],
        "wer": row[-1] / len(ref),
    }


def evaluate(cases):
    results = []
    for case in cases:
        try:
            validate_notes(case["notes"], case["transcript"])
            valid = True
        except PipelineError:
            valid = False
        results.append(
            {"case": case["name"], "passed": valid == case["expected_valid"]}
        )
    return {
        "mode": "synthetic_grounding_checks",
        "cases": len(results),
        "passed": sum(x["passed"] for x in results),
        "results": results,
        "scope": "Structure and evidence-span validation; not factual equivalence or live model quality.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio")
    parser.add_argument("--reference")
    args = parser.parse_args()
    if args.audio:
        from audio_transcription import transcribe_audio

        result = transcribe_audio(Path(args.audio))
        report = {
            "mode": "live_local_audio",
            "language": result["language"],
            "duration_seconds": result["duration_seconds"],
            "segments": len(result["segments"]),
            "scope": "One audio smoke example, not a deployment benchmark.",
        }
        if args.reference:
            report.update(
                word_error_rate(Path(args.reference).read_text(), result["content"])
            )
        print(json.dumps(report, indent=2))
        return 0
    result = evaluate(json.loads(Path(__file__).with_name("cases.json").read_text()))
    print(json.dumps(result, indent=2))
    return 0 if result["cases"] == result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
