"""Compare extraction prediction JSON files against the provided ground truth.

Usage from the repo root:

    python backend/scripts/evaluate_extraction.py --predictions tmp/predictions

The predictions directory should contain one JSON file per document, named either
``doc_001.json`` or ``doc_001_pred.json``. Each file may be the raw extraction
result (``{"records": [...]}``) or a completed job response with a ``records``
field. Predictions MUST use the snake_case field names (``treatment_date``,
``total_charges``, …) the API/result schema emits — the ground truth's camelCase
keys are not accepted on the prediction side.

Scoring is positional and uses one consistent record-count policy: every record
position up to the longer of the two record lists is scored, and a field is
credited only when both a ground-truth and a predicted record exist at that
position and their values agree. So under-prediction (including a missing or
empty prediction file) and over-prediction (hallucinated extra records) both
count as full misses — there is no way to score higher by omitting hard documents
or padding extra rows. Numeric values are canonicalised (rounded half-up to
cents) so int/float are comparable, and booleans never match a number.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

FIELDS = [
    ("treatmentDate", "treatment_date"),
    ("cptCodes", "cpt_codes"),
    ("description", "description"),
    ("provider", "provider"),
    ("insurers", "insurers"),
    ("thirdParties", "third_parties"),
    ("totalCharges", "total_charges"),
    ("insPaid", "ins_paid"),
    ("adjustment", "adjustment"),
    ("payments", "payments"),
    ("balance", "balance"),
    ("page", "page"),
]


@dataclass
class Score:
    matched: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return self.matched / self.total if self.total else 0.0


def _normalize(value: Any) -> Any:
    if isinstance(value, bool):
        return ("__bool__", value)
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, list):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: (item is None, type(item).__name__, str(item)))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return ("__nonfinite__", str(value))
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return value


def _prediction_path(predictions: Path, doc_id: str) -> Path | None:
    for name in (f"{doc_id}.json", f"{doc_id}_pred.json"):
        path = predictions / name
        if path.exists():
            return path
    return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(predictions: Path) -> dict[str, Any]:
    overall = Score()
    by_field = {field[0]: Score() for field in FIELDS}
    by_doc: dict[str, Any] = {}
    seen_doc_ids: set[str] = set()

    for gt_path in sorted(DATA_DIR.glob("*_gt.json")):
        gt = _load_json(gt_path)
        doc_id = gt["doc_id"]
        if doc_id in seen_doc_ids:
            raise ValueError(
                f"Duplicate doc_id {doc_id!r} across ground-truth files "
                f"(at {gt_path.name}); doc_ids must be unique."
            )
        seen_doc_ids.add(doc_id)

        gt_records = gt.get("records", [])
        pred_path = _prediction_path(predictions, doc_id)
        missing = pred_path is None
        pred_records = [] if missing else _load_json(pred_path).get("records", [])

        doc_score = Score()
        for index in range(max(len(gt_records), len(pred_records))):
            expected = gt_records[index] if index < len(gt_records) else None
            actual = pred_records[index] if index < len(pred_records) else None
            for gt_name, pred_name in FIELDS:
                if expected is None or actual is None:
                    matched = False
                else:
                    matched = _normalize(expected.get(gt_name)) == _normalize(
                        actual.get(pred_name)
                    )
                overall.total += 1
                doc_score.total += 1
                by_field[gt_name].total += 1
                if matched:
                    overall.matched += 1
                    doc_score.matched += 1
                    by_field[gt_name].matched += 1

        by_doc[doc_id] = {
            "status": "missing_prediction" if missing else "scored",
            "records_expected": len(gt_records),
            "records_predicted": len(pred_records),
            "field_accuracy": round(doc_score.accuracy, 4),
        }

    return {
        "overall_field_accuracy": round(overall.accuracy, 4),
        "matched_fields": overall.matched,
        "total_fields": overall.total,
        "by_field": {
            name: {
                "accuracy": round(score.accuracy, 4),
                "matched": score.matched,
                "total": score.total,
            }
            for name, score in by_field.items()
        },
        "by_doc": by_doc,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path)
    args = parser.parse_args()

    if not args.predictions.exists():
        raise SystemExit(f"Predictions directory not found: {args.predictions}")

    print(json.dumps(evaluate(args.predictions), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
