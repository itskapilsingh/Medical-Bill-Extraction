from app.ai.deterministic_extractor import try_deterministic_extract
from app.ai.types import Document, Page


def _doc(text: str) -> Document:
    return Document(doc_id="test-doc", num_pages=1, pages=[Page(page_num=1, page_content=text)])


def test_claim_ledger_preserves_modifiers_and_wrapped_insurer():
    result = try_deterministic_extract(
        _doc(
            """
RECORDS CUSTODIAN:
Smith Medical, PC (Billing Records)
** CLAIM 123456 **
Office visit / Blue River Health
123456 99214,25 01/02/2024 CHARGE JONES AMY $100.00
Plan
PAYMENT ACH ****1234 $-70.00
ADJUST CONTRACTUAL (10000) $-20.00
CLAIM TOTAL: $100.00 $70.00 $20.00 $10.00
"""
        )
    )

    assert result is not None
    record = result.records[0]
    assert record.cpt_codes == ["99214,25"]
    assert record.insurers == ["Blue River Health Plan"]
    assert record.balance == 10.0
    assert record.payments is None


def test_claim_ledger_uses_insurance_payment_when_first_service_has_no_named_payer():
    result = try_deterministic_extract(
        _doc(
            """
RECORDS CUSTODIAN:
Smith Medical, PC (Billing Records)
** CLAIM 123456 **
Office visit / Insurance
123456 99214 01/02/2024 CHARGE JONES AMY $100.00
Payment
PAYMENT ACH ****1234 $-70.00
ADJUST CONTRACTUAL (10000) $-30.00
CLAIM TOTAL: $100.00 $70.00 $30.00 $0.00
"""
        )
    )

    assert result is not None
    assert result.records[0].insurers == ["Insurance Payment"]


def test_claim_ledger_uses_first_service_payer_for_mixed_claim():
    result = try_deterministic_extract(
        _doc(
            """
RECORDS CUSTODIAN:
Smith Medical, PC (Billing Records)
** CLAIM 123456 **
Office visit / Insurance
123456 99214 01/02/2024 CHARGE JONES AMY $100.00
Payment
PAYMENT ACH ****1234 $-70.00
ADJUST CONTRACTUAL (10000) $-30.00
Suture removal / Blue River Health
123456 15851 01/02/2024 CHARGE JONES AMY $50.00
Plan
PAYMENT ACH ****1234 $-35.00
ADJUST CONTRACTUAL (10000) $-15.00
CLAIM TOTAL: $150.00 $105.00 $45.00 $0.00
"""
        )
    )

    assert result is not None
    assert result.records[0].insurers == ["Insurance Payment"]


def test_claim_ledger_reads_wrapped_slash_payer_before_generic_rows():
    result = try_deterministic_extract(
        _doc(
            """
RECORDS CUSTODIAN:
Smith Medical, PC (Billing Records)
** CLAIM 123456 **
Hospital discharge day
management, more than 30
123456 99239 01/02/2024 CHARGE BEAN STEPHEN $550.29 $40.34
min / Molina Healthcare of
NY
PAYMENT ACH ****1234 $-377.40
ADJUST CONTRACTUAL (10000) $-132.55
Ultrasound abdomen,
123456 76705 01/02/2024 CHARGE BEAN STEPHEN $566.48 $53.02
limited / Insurance Payment
PAYMENT ACH ****1234 $-286.11
ADJUST CONTRACTUAL (10000) $-227.35
CLAIM TOTAL: $1116.77 $663.51 $359.90 $93.36
"""
        )
    )

    assert result is not None
    assert result.records[0].insurers == ["Molina Healthcare of NY"]


def test_account_ledger_uses_subtotal_and_date_range():
    result = try_deterministic_extract(
        _doc(
            """
Any Imaging Associates, Inc. Patient Billing Statement
Patient Name Date of Birth Insurance
Diane Taylor 07/27/1966 North Star Coverage
Account # 519453
Date of CPT Patient
Description Insurance Charge Ins Paid Adj
Service Code Bal
01/31/2024 73562 X-ray knee, 3 views North Star Coverage $80.00 $50.00 $30.00 $0.00
02/02/2024 73100 X-ray wrist, 2 views North Star Coverage $20.00 $10.00 $5.00 $5.00
Account Subtotal: $100.00 $60.00 $35.00 $5.00
"""
        )
    )

    assert result is not None
    record = result.records[0]
    assert record.treatment_date == "01/31/2024 - 02/02/2024"
    assert record.cpt_codes == ["73562", "73100"]
    assert record.insurers == ["North Star Coverage"]


def test_admission_statement_continues_wrapped_diagnosis():
    result = try_deterministic_extract(
        _doc(
            """
General Care Patient Account Statement
Insurance: Valley Mutual Plan
Admission: 01/01/2024 | Discharge: 01/03/2024 | Diagnosis: Chronic obstructive pulmonary disease with acute
exacerbation
Rev
Date Description Qty Unit Charge Total Charge
Payment Summary
Total Charges: $100.00 Insurance Paid: $60.00
Contractual Adj: $40.00 Patient Balance: $0.00
"""
        )
    )

    assert result is not None
    assert (
        result.records[0].description
        == "Chronic obstructive pulmonary disease with acute exacerbation"
    )


def test_pharmacy_summary_uses_explicit_payment_summary_and_wrapped_parties():
    result = try_deterministic_extract(
        _doc(
            """
Metro Care Pharmacy Pharmacy Expense Report
Patient: Gregory Tate DOB: 10/24/1959 ID: 23033
Date Rx # Drug NDC Prescriber Qty Days Charge 3rd Party
01/04/2023 7380211 Amoxicillin 500mg 00093-0815-01 SAUNDERS APRIL 14 90 $281.08 Local Discount (BIN 123456)
12/31/2024 6752873 Calcium Acetate 667mg 00228-2975-11 BRYAN ANGELA 28 30 $353.81 River PBM (BIN 654321)
Payment Summary
Patient Paid $10.00
Insurance Paid $20.00
Others (Third Parties) $30.00
Grand Total $60.00
"""
        )
    )

    assert result is not None
    record = result.records[0]
    assert record.treatment_date == "01/04/2023 - 12/31/2024"
    assert record.total_charges == 60.0
    assert record.ins_paid == 20.0
    assert record.adjustment == 30.0
    assert record.payments == 10.0
    assert sorted(record.third_parties) == [
        "Local Discount",
        "River PBM",
    ]
