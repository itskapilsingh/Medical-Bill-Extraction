"""The page classifier steers the agent past noise to the billing pages. These
pin the signals taken from the real sample documents."""

from app.ai.page_kinds import BILLING_KINDS, NOISE_KINDS, classify_page


def test_cover_and_certification():
    assert classify_page("FAKITAS RECORDS PERTAINING TO: Jane Doe") == "cover"
    assert classify_page("RECORDS CUSTODIAN: Newton Rehabilitation Center") == "cover"
    assert classify_page("Certification of Records\nPlease complete...") == "certification"


def test_lab_report():
    text = "Laboratory Report Collection Date: 04/03/2026\nTest Name Value Reference Range"
    assert classify_page(text) == "lab_report"


def test_billing_ledger():
    text = "Newton Rehabilitation Center\nBilling Summary\nClaim ID 731262\nClaim Total: $493.20"
    assert classify_page(text) == "billing_ledger"


def test_pharmacy_ledger():
    text = "WILSON MEDICAL PHARMACY\nRX # FILL DATE PRESCRIBER DRUG NAME NDC QTY CHARGE 3RD PARTY"
    assert classify_page(text) == "pharmacy_ledger"


def test_prescription_is_not_mistaken_for_pharmacy():
    text = "Dr. Thompson & Associates\nPrescriber: Thompson Wendy\nNPI: 7745949301\nDiagnosis: J06.9"
    assert classify_page(text) == "prescription"


def test_empty_and_other():
    assert classify_page("") == "empty"
    assert classify_page("   \n  ") == "empty"
    assert classify_page("Some unrelated page of prose.") == "other"


def test_kind_sets_are_disjoint_and_cover_intent():
    assert BILLING_KINDS == {"billing_ledger", "pharmacy_ledger"}
    assert "cover" in NOISE_KINDS and "lab_report" in NOISE_KINDS
    assert BILLING_KINDS.isdisjoint(NOISE_KINDS)
