"""Tests for the accuracy eval harness (docs/design.md §7).

``backend/scripts/evaluate_extraction.py`` is the artifact §7 reports against: it
diffs prediction JSON files against the ``data/*_gt.json`` ground truth and
produces overall / per-field / per-document field accuracy. These tests pin its
scoring contract — normalization, the camelCase-gt → snake_case-pred mapping,
positional record comparison, and how it treats missing/short/over-long
predictions — using synthetic fixtures so they never touch the real PHI data set.

The script lives in ``backend/scripts`` (not an importable package), so it is
loaded by path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_extraction.py"
_spec = importlib.util.spec_from_file_location("evaluate_extraction", _MODULE_PATH)
assert _spec and _spec.loader
ee = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve the module via sys.modules.
sys.modules[_spec.name] = ee
_spec.loader.exec_module(ee)


# --------------------------------------------------------------------------- fixtures

def gt_record(**overrides) -> dict:
    """A complete ground-truth record (camelCase keys, as in data/*_gt.json)."""
    base = {
        "treatmentDate": "2026-01-02",
        "cptCodes": ["99213"],
        "description": "Office visit",
        "provider": "Acme Health",
        "insurers": ["Aetna"],
        "thirdParties": [],
        "totalCharges": 100.0,
        "insPaid": 80.0,
        "adjustment": 10.0,
        "payments": 5.0,
        "balance": 5.0,
        "page": "1",
    }
    base.update(overrides)
    return base


def pred_record(**overrides) -> dict:
    """A complete prediction record (snake_case keys, as the API/result emits)."""
    base = {
        "treatment_date": "2026-01-02",
        "cpt_codes": ["99213"],
        "description": "Office visit",
        "provider": "Acme Health",
        "insurers": ["Aetna"],
        "third_parties": [],
        "total_charges": 100.0,
        "ins_paid": 80.0,
        "adjustment": 10.0,
        "payments": 5.0,
        "balance": 5.0,
        "page": "1",
    }
    base.update(overrides)
    return base


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Point the harness at a temp data dir and give helpers to seed gt/pred files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    preds_dir = tmp_path / "preds"
    preds_dir.mkdir()
    monkeypatch.setattr(ee, "DATA_DIR", data_dir)

    def write_gt(doc_id: str, records: list[dict]) -> None:
        (data_dir / f"{doc_id}_gt.json").write_text(
            json.dumps({"doc_id": doc_id, "records": records}), encoding="utf-8"
        )

    def write_pred(doc_id: str, records: list[dict], *, suffix: str = "") -> None:
        (preds_dir / f"{doc_id}{suffix}.json").write_text(
            json.dumps({"records": records}), encoding="utf-8"
        )

    return type(
        "Harness",
        (),
        {"data_dir": data_dir, "preds": preds_dir, "write_gt": staticmethod(write_gt),
         "write_pred": staticmethod(write_pred), "run": staticmethod(lambda: ee.evaluate(preds_dir))},
    )


# ------------------------------------------------------------------------ _normalize

def test_normalize_collapses_string_whitespace():
    assert ee._normalize("  Acme   Health  ") == "Acme Health"


def test_normalize_sorts_lists_order_insensitively():
    assert ee._normalize(["Bravo", "Alpha"]) == ["Alpha", "Bravo"]


def test_normalize_normalizes_then_sorts_list_items():
    # Items are whitespace-collapsed before sorting.
    assert ee._normalize(["  b  b ", "a"]) == ["a", "b b"]


def test_normalize_rounds_floats_to_cents():
    assert ee._normalize(12.3456) == 12.35
    assert ee._normalize(100.0) == 100.0


def test_normalize_none_passthrough_and_numeric_canonicalization():
    assert ee._normalize(None) is None
    # int and float of the same amount canonicalize to one comparable value.
    assert ee._normalize(7) == ee._normalize(7.0) == 7.0


def test_normalize_rounds_half_up_not_bankers():
    # round(2.675, 2) is 2.67 in binary float; the harness rounds HALF-UP to 2.68.
    assert ee._normalize(2.675) == 2.68
    assert ee._normalize(0.125) == 0.13


def test_normalize_rejects_bool_as_a_number():
    # bool is an int subclass; True/False must never match 1/0 as a numeric value.
    assert ee._normalize(True) != ee._normalize(1)
    assert ee._normalize(True) != ee._normalize(1.0)
    assert ee._normalize(False) != ee._normalize(0)
    assert ee._normalize(True) == ee._normalize(True)  # two bools still compare equal


def test_normalize_non_finite_numbers_do_not_crash():
    # json.loads accepts bare Infinity/-Infinity/NaN; these must not raise (Decimal
    # can't quantize a non-finite value) and must never match a finite amount.
    for bad in (float("inf"), float("-inf"), float("nan")):
        assert ee._normalize(bad) != ee._normalize(100.0)


# ----------------------------------------------------------------------------- Score

def test_score_accuracy_is_zero_when_empty():
    assert ee.Score().accuracy == 0.0


def test_score_accuracy_ratio():
    assert ee.Score(matched=3, total=4).accuracy == 0.75


# -------------------------------------------------------------- _prediction_path

def test_prediction_path_prefers_plain_name_then_pred_suffix(tmp_path):
    (tmp_path / "doc_001_pred.json").write_text("{}", encoding="utf-8")
    assert ee._prediction_path(tmp_path, "doc_001").name == "doc_001_pred.json"
    (tmp_path / "doc_001.json").write_text("{}", encoding="utf-8")
    # When both exist the plain "<doc>.json" wins.
    assert ee._prediction_path(tmp_path, "doc_001").name == "doc_001.json"


def test_prediction_path_returns_none_when_absent(tmp_path):
    assert ee._prediction_path(tmp_path, "doc_404") is None


# -------------------------------------------------------------------- evaluate()

def test_perfect_match_scores_full_accuracy(harness):
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record()])

    result = harness.run()

    assert result["overall_field_accuracy"] == 1.0
    assert result["matched_fields"] == result["total_fields"] == 12
    assert all(f["accuracy"] == 1.0 for f in result["by_field"].values())
    assert result["by_doc"]["doc_001"] == {
        "status": "scored",
        "records_expected": 1,
        "records_predicted": 1,
        "field_accuracy": 1.0,
    }


def test_single_wrong_field_is_isolated(harness):
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record(provider="Wrong Clinic")])

    result = harness.run()

    assert result["matched_fields"] == 11
    assert result["total_fields"] == 12
    assert result["by_field"]["provider"] == {"accuracy": 0.0, "matched": 0, "total": 1}
    assert result["by_field"]["totalCharges"]["accuracy"] == 1.0


def test_normalization_makes_equivalent_values_match(harness):
    harness.write_gt(
        "doc_001",
        [gt_record(provider="Acme  Health", insurers=["Aetna", "Cigna"], totalCharges=12.3456)],
    )
    # Different spacing, list order, and float precision — all should normalize equal.
    harness.write_pred(
        "doc_001",
        [pred_record(provider=" Acme Health ", insurers=["Cigna", "Aetna"], total_charges=12.35)],
    )

    result = harness.run()
    assert result["overall_field_accuracy"] == 1.0
    # Guard against an accidentally-trivial (shrunken/empty) comparison set passing
    # itself off as a perfect score.
    assert result["matched_fields"] == result["total_fields"] == 12


# The 5 fields whose gt (camelCase) and prediction (snake_case) keys differ. A
# prediction that (wrongly) uses the gt camelCase keys cannot satisfy these.
_CAMEL_ONLY_FIELDS = ["treatmentDate", "cptCodes", "thirdParties", "totalCharges", "insPaid"]


def test_prediction_must_use_snake_case_keys(harness):
    # Predictions are scored against the snake_case contract only — there is NO
    # fallback into the ground-truth's camelCase namespace, so a gt-shaped
    # (camelCase) prediction cannot self-validate: the 5 fields whose keys differ
    # score 0; only the 7 fields whose key coincides still match.
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [gt_record()])  # camelCase — wrong contract

    result = harness.run()
    for field in _CAMEL_ONLY_FIELDS:
        assert result["by_field"][field]["matched"] == 0, field
    assert result["matched_fields"] == 7
    assert result["total_fields"] == 12


def test_short_prediction_penalizes_missing_records(harness):
    # gt has 2 records, prediction only 1: the un-predicted second record is scored
    # as all-missed, so it IS penalized.
    harness.write_gt("doc_001", [gt_record(), gt_record(page="2")])
    harness.write_pred("doc_001", [pred_record()])

    result = harness.run()
    doc = result["by_doc"]["doc_001"]
    assert doc["records_expected"] == 2
    assert doc["records_predicted"] == 1
    assert result["total_fields"] == 24  # 2 records x 12 fields
    assert result["matched_fields"] == 12  # only the first record matches


def test_over_prediction_is_penalized(harness):
    # gt has 1 record, prediction has 2: the surplus (hallucinated) record is
    # scored against an absent ground truth, so all its fields miss — over-
    # prediction costs accuracy rather than being free.
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record(), pred_record(provider="Extra")])

    result = harness.run()
    assert result["total_fields"] == 24          # max(1, 2) records x 12 fields
    assert result["matched_fields"] == 12         # only the real record matches
    assert result["by_field"]["provider"]["matched"] == 1
    assert result["by_doc"]["doc_001"]["records_predicted"] == 2
    assert result["by_doc"]["doc_001"]["field_accuracy"] == 0.5


def test_missing_prediction_file_is_penalized_not_excluded(harness):
    # A doc with no prediction file is treated as predicting nothing: its records
    # are all-missed and counted, so omitting it can't score higher than an empty
    # prediction. The status still flags it as missing for the operator.
    harness.write_gt("doc_001", [gt_record(), gt_record()])

    result = harness.run()
    assert result["by_doc"]["doc_001"] == {
        "status": "missing_prediction",
        "records_expected": 2,
        "records_predicted": 0,
        "field_accuracy": 0.0,
    }
    assert result["total_fields"] == 24
    assert result["matched_fields"] == 0
    assert result["overall_field_accuracy"] == 0.0


def test_multiple_docs_aggregate_overall_and_per_field(harness):
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record()])  # 12/12
    harness.write_gt("doc_002", [gt_record()])
    harness.write_pred("doc_002", [pred_record(provider="X", balance=999.0)])  # 10/12

    result = harness.run()
    assert result["total_fields"] == 24
    assert result["matched_fields"] == 22
    assert result["overall_field_accuracy"] == round(22 / 24, 4)
    assert result["by_field"]["provider"]["matched"] == 1   # doc_001 only
    assert result["by_field"]["balance"]["matched"] == 1
    assert result["by_doc"]["doc_002"]["field_accuracy"] == round(10 / 12, 4)


def test_duplicate_doc_id_across_gt_files_raises(harness):
    # doc_id keys both the report and the prediction lookup; two gt files sharing
    # one is a data error the harness must reject loudly, not silently merge.
    harness.write_gt("doc_001", [gt_record()])
    (harness.data_dir / "doc_001_copy_gt.json").write_text(
        json.dumps({"doc_id": "doc_001", "records": [gt_record(page="2")]}),
        encoding="utf-8",
    )
    harness.write_pred("doc_001", [pred_record()])

    with pytest.raises(ValueError, match="Duplicate doc_id"):
        harness.run()


# ------------------------------------------------ list normalization safety (regression)

def test_normalize_tolerates_none_and_mixed_type_lists():
    # A list field carrying a null (e.g. an insurer list with an unknown payer) or
    # mixed types (CPT codes serialized as ints) must NOT raise — a single such
    # value used to abort the entire eval via TypeError inside sorted().
    assert ee._normalize(["Aetna", None]) == ["Aetna", None]
    assert ee._normalize([None, "Aetna"]) == ["Aetna", None]  # order-insensitive
    assert ee._normalize([99213, "99214"]) == [99213, "99214"]
    assert ee._normalize([None, None]) == [None, None]


def test_evaluate_does_not_crash_on_null_in_list_field(harness):
    # End-to-end: a record whose insurers list contains null is scored, not fatal,
    # and still compares order-insensitively.
    harness.write_gt("doc_001", [gt_record(insurers=["Aetna", None])])
    harness.write_pred("doc_001", [pred_record(insurers=[None, "Aetna"])])

    result = harness.run()  # raised TypeError before the total-order sort fix
    assert result["by_field"]["insurers"]["matched"] == 1
    assert result["overall_field_accuracy"] == 1.0


def test_evaluate_scores_non_finite_prediction_as_miss_not_crash(harness):
    # A non-finite predicted amount (json.loads accepts bare Infinity) must score
    # as a miss for that field, NOT abort scoring for the whole run.
    harness.write_gt("doc_001", [gt_record(totalCharges=100.0)])
    (harness.preds / "doc_001.json").write_text(
        '{"records": [{"total_charges": Infinity, "page": "1"}]}', encoding="utf-8"
    )

    result = harness.run()  # would raise decimal.InvalidOperation before the guard
    assert result["by_doc"]["doc_001"]["status"] == "scored"
    assert result["by_field"]["totalCharges"]["matched"] == 0
    assert result["by_field"]["page"]["matched"] == 1


# ------------------------------------------------- evaluate() wiring & edge cases

def test_evaluate_resolves_pred_suffix_filename(harness):
    # The docstring advertises "<doc>_pred.json" as a valid prediction filename;
    # drive evaluate() (not just _prediction_path in isolation) through that path.
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record()], suffix="_pred")

    result = harness.run()
    assert result["by_doc"]["doc_001"]["status"] == "scored"
    assert result["by_doc"]["doc_001"]["records_predicted"] == 1
    assert result["overall_field_accuracy"] == 1.0


def test_evaluate_accepts_full_job_response_shaped_prediction(harness):
    # The docstring promises a prediction file may be a completed job response
    # (records alongside envelope keys), not just a raw {"records": [...]}.
    harness.write_gt("doc_001", [gt_record()])
    (harness.preds / "doc_001.json").write_text(
        json.dumps(
            {
                "job_id": "j1",
                "status": "completed",
                "created_at": "2026-01-02T00:00:00Z",
                "document": {"filename": "x.pdf"},
                "records": [pred_record()],
            }
        ),
        encoding="utf-8",
    )

    result = harness.run()
    assert result["by_doc"]["doc_001"]["status"] == "scored"
    assert result["overall_field_accuracy"] == 1.0


def test_null_gt_field_with_absent_prediction_field_counts_as_matched(harness):
    # DOCUMENTS current behaviour: a null ground-truth field and a prediction that
    # omits that key both normalize to None and score as a match — the model gets
    # credit for correctly not inventing a value.
    harness.write_gt("doc_001", [gt_record(adjustment=None)])
    pred = {key: value for key, value in pred_record().items() if key != "adjustment"}
    harness.write_pred("doc_001", [pred])

    result = harness.run()
    assert result["by_field"]["adjustment"]["matched"] == 1
    assert result["overall_field_accuracy"] == 1.0


def test_unpredicted_record_earns_no_credit_even_for_null_fields(harness):
    # A wholly UN-predicted record earns NO credit — not even for its null fields.
    # (A present-but-incomplete record is different: see the null-field test above,
    # where omitting a key whose gt value is null still counts as matched.)
    second = gt_record(page="2", insPaid=None, adjustment=None, payments=None, balance=None)
    harness.write_gt("doc_001", [gt_record(), second])
    harness.write_pred("doc_001", [pred_record()])  # only the first record

    result = harness.run()
    assert result["matched_fields"] == 12  # record 1 only; record 2 is all-miss
    assert result["total_fields"] == 24


def test_missing_doc_is_penalized_without_contaminating_scored_docs(harness):
    # An interleaved missing-prediction doc is counted as all-missed (penalized)
    # but does not corrupt the other docs' per-doc numbers.
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record()])           # 12/12
    harness.write_gt("doc_002", [gt_record()])               # no prediction -> 0/12
    harness.write_gt("doc_003", [gt_record()])
    harness.write_pred("doc_003", [pred_record(provider="X", balance=999.0)])  # 10/12

    result = harness.run()
    assert result["total_fields"] == 36              # 3 docs x 1 record x 12 fields
    assert result["matched_fields"] == 22            # 12 + 0 + 10
    assert result["overall_field_accuracy"] == round(22 / 36, 4)
    assert result["by_doc"]["doc_002"] == {
        "status": "missing_prediction",
        "records_expected": 1,
        "records_predicted": 0,
        "field_accuracy": 0.0,
    }
    assert result["by_doc"]["doc_001"]["field_accuracy"] == 1.0
    assert result["by_doc"]["doc_003"]["field_accuracy"] == round(10 / 12, 4)


def test_empty_gt_with_a_prediction_penalizes_the_hallucinated_record(harness):
    # gt has zero records but the model predicted one: that surplus record is a
    # false positive, scored as all-missed.
    harness.write_gt("doc_001", [])
    harness.write_pred("doc_001", [pred_record()])

    result = harness.run()
    assert result["by_doc"]["doc_001"] == {
        "status": "scored",
        "records_expected": 0,
        "records_predicted": 1,
        "field_accuracy": 0.0,
    }
    assert result["total_fields"] == 12
    assert result["matched_fields"] == 0


def test_page_field_mismatch_is_scored(harness):
    # The 12th field (page) is otherwise only covered incidentally by perfect-match
    # cases; isolate a page-only mismatch so its scoring is explicit.
    harness.write_gt("doc_001", [gt_record(page="1")])
    harness.write_pred("doc_001", [pred_record(page="7")])

    result = harness.run()
    assert result["by_field"]["page"] == {"accuracy": 0.0, "matched": 0, "total": 1}
    assert result["matched_fields"] == 11


# ---------------------------------------------------------------------------- main()

def test_main_errors_on_missing_predictions_dir(harness, monkeypatch, tmp_path):
    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr(sys, "argv", ["evaluate_extraction.py", "--predictions", str(missing)])
    with pytest.raises(SystemExit):
        ee.main()


def test_main_requires_predictions_arg(harness, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluate_extraction.py"])
    with pytest.raises(SystemExit):
        ee.main()


def test_main_prints_json_report_and_returns_zero(harness, monkeypatch, capsys):
    harness.write_gt("doc_001", [gt_record()])
    harness.write_pred("doc_001", [pred_record()])
    monkeypatch.setattr(
        sys, "argv", ["evaluate_extraction.py", "--predictions", str(harness.preds)]
    )

    code = ee.main()

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["overall_field_accuracy"] == 1.0
    assert set(report) >= {"overall_field_accuracy", "by_field", "by_doc", "total_fields"}
