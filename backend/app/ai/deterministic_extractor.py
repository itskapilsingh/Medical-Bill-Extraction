from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.ai.types import Document
from app.models.extraction import BillingRecord, ExtractionOutput

MONEY_RE = r"\$([0-9][0-9,]*\.\d{2})"
DATE_RE = r"\d{2}/\d{2}/\d{4}"
CODE_RE = r"[A-Z]?\d{4,5}(?:,\d{2})?"


@dataclass(frozen=True)
class PageSpan:
    page_num: int
    start: int
    end: int


def try_deterministic_extract(document: Document) -> ExtractionOutput | None:
    """Extract known billing table formats without model calls.

    Some billing packets use machine-readable ledger layouts. For those layouts,
    regexing visible summary rows is safer than asking the agent to remember
    hundreds of rows. Unknown formats deliberately return ``None`` so the
    existing LLM path remains the fallback.
    """

    text, page_spans = _document_text(document)
    if _has_claim_ledger(text):
        return _parse_claim_ledger(text, page_spans)
    if "Account Total:" in text or "Account Subtotal:" in text:
        return _parse_account_ledger(text, page_spans)
    if "Payment Summary" in text and "Admission:" in text:
        return _parse_admission_statement(text, page_spans)
    if "Inpatient Episode:" in text and "Total Charges" in text:
        return _parse_inpatient_statement(text, page_spans)
    if _has_dialysis_periods(text):
        return _parse_dialysis_statement(text, page_spans)
    if _has_pharmacy_ledger(text):
        return _parse_pharmacy_statement(text, page_spans)
    return None


def _document_text(document: Document) -> tuple[str, list[PageSpan]]:
    parts: list[str] = []
    spans: list[PageSpan] = []
    cursor = 0
    for page in document.pages:
        if parts:
            parts.append("\n")
            cursor += 1
        start = cursor
        parts.append(page.page_content)
        cursor += len(page.page_content)
        spans.append(PageSpan(page_num=page.page_num, start=start, end=cursor))
    return "".join(parts), spans


def _has_claim_ledger(text: str) -> bool:
    return bool(
        re.search(r"(?im)^\s*Claim Total:", text)
        or re.search(r"(?im)^\s*CLAIM TOTAL:", text)
    )


def _has_dialysis_periods(text: str) -> bool:
    return bool(
        re.search(r"(?i)Period Total Charges:", text)
        or re.search(r"(?im)^\s*PERIOD TOTAL:", text)
    )


def _has_pharmacy_ledger(text: str) -> bool:
    return bool(
        ("Pharmacy" in text or "PHARMACY" in text)
        and (
            "RX # FILL DATE" in text
            or "Rx # Date" in text
            or "Prescription Fill History" in text
            or "Pharmacy Expense Report" in text
        )
    )


def _money(value: str) -> float:
    decimal = Decimal(value.replace(",", "")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(decimal)


def _money_from_match(match: re.Match[str], group: int = 1) -> float:
    return _money(match.group(group))


def _date_key(value: str) -> datetime:
    return datetime.strptime(value, "%m/%d/%Y")


def _date_range(dates: list[str]) -> str:
    ordered = sorted(dates, key=_date_key)
    return f"{ordered[0]} - {ordered[-1]}"


def _page_range(page_spans: list[PageSpan], start: int, end: int) -> str:
    pages = [
        span.page_num
        for span in page_spans
        if span.start < end and span.end > start
    ]
    if not pages:
        return ""
    first = min(pages)
    last = max(pages)
    return str(first) if first == last else f"{first}-{last}"


def _provider_from_custodian(text: str) -> str | None:
    match = re.search(r"(?im)^RECORDS CUSTODIAN:\s*\n(.+?)(?:\s+\(Billing Records\))?$", text)
    if match:
        return _clean_provider(match.group(1))
    return None


def _clean_provider(value: str) -> str:
    value = re.sub(r"\s+\(Billing Records\)$", "", value.strip())
    if value.isupper():
        return value.title().replace(", Pc", ", PC")
    return value


def _provider_from_statement(text: str) -> str:
    custodian = _provider_from_custodian(text)
    if custodian:
        return custodian
    first_non_empty = next(line.strip() for line in text.splitlines() if line.strip())
    first_non_empty = re.sub(
        r"\s+(?:Patient Billing Statement|Patient Account Statement|Pharmacy Expense Report)$",
        "",
        first_non_empty,
        flags=re.I,
    )
    return _clean_provider(first_non_empty)


def _find_insurer(text: str) -> str | None:
    labeled = _labeled_payer(text)
    if labeled:
        return labeled
    insurance_payment = _insurance_payment_label(text)
    if insurance_payment:
        return insurance_payment
    return None


def _labeled_payer(text: str) -> str | None:
    label_match = re.search(
        r"(?im)\b(?:Insurer|Payer|Insurance|Ins)\s*:\s*([A-Za-z][^\n|]*)",
        text,
    )
    if label_match:
        payer = _clean_payer(label_match.group(1))
        if payer:
            return payer

    table_match = re.search(
        rf"(?im)^Patient Name\s+Date of Birth\s+Insurance\s*\n.+?{DATE_RE}\s+([A-Za-z][^\n]+)$",
        text,
    )
    if table_match:
        payer = _clean_payer(table_match.group(1))
        if payer:
            return payer

    inline_match = re.search(
        rf"(?im)^.*\bInsurance\s+([A-Za-z][A-Za-z &./'-]*?)\s*$",
        text,
    )
    if inline_match:
        payer = _clean_payer(inline_match.group(1))
        if payer:
            return payer
    return None


def _insurance_payment_label(text: str) -> str | None:
    if (
        re.search(r"\bInsurance\b", text, flags=re.I)
        and re.search(r"\bPayment\b", text, flags=re.I)
        and not re.search(r"\bInsurance Paid\b|\bInsurance Payments\b", text, flags=re.I)
    ):
        return "Insurance Payment"
    return None


def _clean_payer(value: str) -> str | None:
    value = " ".join(value.strip().split())
    value = re.split(
        r"\b(?:DOB|Date of Birth|Patient|Patient ID|ID|Phone|Tel|Order|Ref|Plan Type|Due Date|Amount|Paid|Charge|Adj)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = value.strip(" :-—|,.;")
    value = re.sub(r"\s+\([A-Z0-9 -]+\)$", "", value)
    if not value or value.lower() in {
        "insurance",
        "ins",
        "payer",
        "plan",
        "payment",
        "reason",
    }:
        return None
    if re.search(r"\d", value):
        return None
    return value


def _segment_by_markers(
    text: str, marker_pattern: str
) -> list[tuple[str, str, int, int]]:
    matches = list(re.finditer(marker_pattern, text, flags=re.I | re.M))
    segments: list[tuple[str, str, int, int]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segments.append((match.group(1), text[match.start() : end], match.start(), end))
    return segments


def _parse_claim_ledger(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    marker = r"(?im)^\s*(?:Claim ID\s+(\d+)|\*\*\s*CLAIM\s+(\d+)\s*\*\*)"
    raw_matches = list(re.finditer(marker, text))
    segments: list[tuple[str, str, int, int]] = []
    for index, match in enumerate(raw_matches):
        claim_id = match.group(1) or match.group(2)
        end = raw_matches[index + 1].start() if index + 1 < len(raw_matches) else len(text)
        segments.append((claim_id, text[match.start() : end], match.start(), end))

    records: list[BillingRecord] = []
    total_re = re.compile(
        rf"(?im)^\s*Claim Total:\s*{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}"
        rf"|^\s*CLAIM TOTAL:\s*{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}",
        flags=re.M,
    )
    for claim_id, segment, start, end in segments:
        total_match = total_re.search(segment)
        if total_match is None:
            continue
        amounts = [group for group in total_match.groups() if group is not None]
        if len(amounts) != 4:
            continue

        line_re = re.compile(
            rf"(?m)^\s*{re.escape(claim_id)}\s+({CODE_RE})\s+({DATE_RE})\s+.*?\bCHARGE\b"
        )
        line_matches = list(line_re.finditer(segment))
        if not line_matches:
            continue
        cpt_codes = [match.group(1) for match in line_matches]
        treatment_date = line_matches[0].group(2)
        insurer = _claim_insurer(segment, claim_id) or _find_insurer(segment)

        records.append(
            BillingRecord(
                invoice_number=f"Claim {claim_id}",
                treatment_date=treatment_date,
                cpt_codes=cpt_codes,
                description=None,
                provider=provider,
                insurers=[insurer] if insurer else [],
                third_parties=[],
                total_charges=_money(amounts[0]),
                ins_paid=_money(amounts[1]),
                adjustment=_money(amounts[2]),
                payments=None,
                balance=_money(amounts[3]),
                page=_page_range(page_spans, start, end),
            )
        )

    _normalize_claim_record_insurers(records)
    return ExtractionOutput(records=records, flagged=[]) if records else None


def _parse_account_ledger(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    insurer = _find_insurer(text)
    segments = _segment_by_markers(text, r"(?im)^\s*Account\s+(?:#\s*)?(\d+)\s*$")
    records: list[BillingRecord] = []
    total_re = re.compile(
        rf"(?im)^\s*Account (?:Total|Subtotal):\s*{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}"
    )
    row_re = re.compile(rf"(?m)^\s*({DATE_RE})\s+({CODE_RE})\b.*?{MONEY_RE}")
    for account_id, segment, start, end in segments:
        total_match = total_re.search(segment)
        rows = list(row_re.finditer(segment))
        if total_match is None or not rows:
            continue
        dates = [match.group(1) for match in rows]
        cpt_codes = [match.group(2) for match in rows]
        records.append(
            BillingRecord(
                invoice_number=f"Account {account_id}",
                treatment_date=_date_range(dates),
                cpt_codes=cpt_codes,
                description=None,
                provider=provider,
                insurers=[insurer] if insurer else [],
                third_parties=[],
                total_charges=_money_from_match(total_match, 1),
                ins_paid=_money_from_match(total_match, 2),
                adjustment=_money_from_match(total_match, 3),
                payments=None,
                balance=_money_from_match(total_match, 4),
                page=_page_range(page_spans, start, end),
            )
        )
    return ExtractionOutput(records=records, flagged=[]) if records else None


def _parse_admission_statement(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    insurer = _find_insurer(text)
    marker = (
        rf"(?im)^Admission:\s*({DATE_RE})\s*\|\s*Discharge:\s*({DATE_RE})\s*\|\s*"
        r"Diagnosis:\s*(.+)$"
    )
    matches = list(re.finditer(marker, text))
    records: list[BillingRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start() : end]
        total_charges = _label_money(segment, r"Total Charges:")
        ins_paid = _label_money(segment, r"Insurance Paid:")
        adjustment = _label_money(segment, r"Contractual Adj:")
        balance = _label_money(segment, r"Patient Balance:")
        if None in (total_charges, ins_paid, adjustment, balance):
            continue
        records.append(
            BillingRecord(
                invoice_number=None,
                treatment_date=f"{match.group(1)} - {match.group(2)}",
                cpt_codes=[],
                description=_continued_diagnosis(segment, match.group(3)),
                provider=provider,
                insurers=[insurer] if insurer else [],
                third_parties=[],
                total_charges=total_charges,
                ins_paid=ins_paid,
                adjustment=adjustment,
                payments=None,
                balance=balance,
                page=_page_range(page_spans, match.start(), end),
            )
        )
    return ExtractionOutput(records=records, flagged=[]) if records else None


def _parse_inpatient_statement(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    insurer = _find_insurer(text)
    marker = rf"(?im)^Inpatient Episode:\s*({DATE_RE})\s*[–-]\s*({DATE_RE})\s*$"
    matches = list(re.finditer(marker, text))
    records: list[BillingRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start() : end]
        diagnosis = re.search(r"(?im)^Diagnosis:\s*(.+)$", segment)
        total_charges = _label_money(segment, r"Total Charges")
        ins_paid = _label_money(segment, r"Insurance Paid")
        adjustment = _label_money(segment, r"Adjustment")
        balance = _label_money(segment, r"Patient Balance")
        if diagnosis is None or None in (total_charges, ins_paid, adjustment, balance):
            continue
        records.append(
            BillingRecord(
                invoice_number=None,
                treatment_date=f"{match.group(1)} - {match.group(2)}",
                cpt_codes=[],
                description=diagnosis.group(1).strip(),
                provider=provider,
                insurers=[insurer] if insurer else [],
                third_parties=[],
                total_charges=total_charges,
                ins_paid=ins_paid,
                adjustment=adjustment,
                payments=None,
                balance=balance,
                page=_page_range(page_spans, match.start(), end),
            )
        )
    return ExtractionOutput(records=records, flagged=[]) if records else None


def _parse_dialysis_statement(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    header = re.compile(
        rf"(?im)^(?:Detail\s+[—-]\s*)?({DATE_RE})\s*(?:to|[–-])\s*({DATE_RE})\s*"
        rf"\|\s*(\d+)\s+TREATMENTS?\s*\|\s*(?:Claim|CLM):\s*(CLM\d+)"
    )
    matches = list(header.finditer(text))
    records: list[BillingRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start() : end]
        total_match = re.search(
            rf"(?im)^\s*(?:Period Total Charges|PERIOD TOTAL):\s*{MONEY_RE}",
            segment,
        )
        ins_match = re.search(rf"(?i)\bIns Paid:\s*{MONEY_RE}", segment)
        adj_match = re.search(
            rf"(?i)Contractual Adj(?:ustment)?\.?\s*\(\s*{MONEY_RE}\s*\)",
            segment,
        )
        balance_match = re.search(rf"(?i)(?:Ending Balance:?|= Ending Balance)\s*{MONEY_RE}", segment)
        insurer_match = re.search(r"(?i)\bInsurer:\s*([A-Za-z][A-Za-z ]+)", segment)
        if not (total_match and ins_match and adj_match and balance_match):
            continue
        insurer = insurer_match.group(1).strip() if insurer_match else _find_insurer(segment)
        treatments = int(match.group(3))
        records.append(
            BillingRecord(
                invoice_number=match.group(4),
                treatment_date=f"{match.group(1)} - {match.group(2)}",
                cpt_codes=[],
                description=f"Dialysis \u2014 {treatments} treatments",
                provider=provider,
                insurers=[insurer] if insurer else [],
                third_parties=[],
                total_charges=_money_from_match(total_match, 1),
                ins_paid=_money_from_match(ins_match, 1),
                adjustment=_money_from_match(adj_match, 1),
                payments=None,
                balance=_money_from_match(balance_match, 1),
                page=_page_range(page_spans, match.start(), end),
            )
        )
    return ExtractionOutput(records=records, flagged=[]) if records else None


def _parse_pharmacy_statement(text: str, page_spans: list[PageSpan]) -> ExtractionOutput | None:
    provider = _provider_from_statement(text)
    billing_text = _pharmacy_billing_text(text)
    dates = re.findall(DATE_RE, billing_text)
    if not dates:
        return None

    summary = _pharmacy_summary(text)
    if summary is None:
        return None
    total_charges, ins_paid, adjustment, payments = summary
    description = "Pharmacy Expense Report" if "Pharmacy Expense Report" in text else "Pharmacy Record"

    return ExtractionOutput(
        records=[
            BillingRecord(
                invoice_number=None,
                treatment_date=_date_range(dates),
                cpt_codes=[],
                description=description,
                provider=provider,
                insurers=[],
                third_parties=_third_parties(text),
                total_charges=total_charges,
                ins_paid=ins_paid,
                adjustment=adjustment,
                payments=payments,
                balance=0.0,
                page=_page_range(page_spans, 0, len(text)),
            )
        ],
        flagged=[],
    )


def _claim_insurer(segment: str, claim_id: str) -> str | None:
    lines = segment.splitlines()
    row_re = re.compile(
        rf"^\s*{re.escape(claim_id)}\s+{CODE_RE}\s+{DATE_RE}\s+.*?\bCHARGE\b.*$",
        re.I,
    )
    for index, line in enumerate(lines):
        if not row_re.search(line):
            continue
        block = _claim_service_block(lines, index)
        payer = _payer_from_service_block(block)
        if payer is None:
            payer = _claim_column_payer(lines, index)
        if payer:
            return payer
    return None


def _normalize_claim_record_insurers(records: list[BillingRecord]) -> None:
    named = [
        record.insurers[0]
        for record in records
        if record.insurers and record.insurers[0] != "Insurance Payment"
    ]
    if not named:
        return

    dominant, count = Counter(named).most_common(1)[0]
    if count < max(2, len(records) // 4):
        return

    dominant_words = set(_name_words(dominant))
    for record in records:
        if not record.insurers:
            continue
        value = record.insurers[0]
        if value == "Insurance Payment" or value == dominant:
            continue
        value_words = set(_name_words(value))
        if (
            value.casefold() in dominant.casefold()
            or dominant.casefold() in value.casefold()
            or bool(value_words & dominant_words)
        ):
            record.insurers = [dominant]


def _name_words(value: str) -> list[str]:
    return [
        word.casefold()
        for word in re.findall(r"[A-Za-z]{3,}", value)
        if word.casefold() not in {"the", "and", "for", "with"}
    ]


def _claim_service_block(lines: list[str], row_index: int) -> str:
    start = max(0, row_index - 2)
    end = row_index + 1
    while end < len(lines):
        if re.match(
            r"(?i)^\s*(?:PAYMENT\s+(?:ACH|CHECK|CARD|\$|#)|ADJUST|CONTRACTUAL|Claim Total:|CLAIM TOTAL:|\*\*\s*CLAIM|Claim ID)",
            lines[end],
        ):
            break
        end += 1
    return "\n".join(lines[start:end])


def _payer_from_service_block(block: str) -> str | None:
    labeled = _labeled_payer(block)
    if labeled:
        return labeled
    slash_payer = _payer_after_slash(block)
    if slash_payer:
        return slash_payer
    return _insurance_payment_label(block)


def _payer_after_slash(block: str) -> str | None:
    flat = " ".join(block.split())
    match = re.search(r"(?:^|\s)/\s*([^$]+?)\s+\$", flat)
    continuation = re.search(
        r"\$\d[\d,]*\.\d{2}\s+([A-Za-z][A-Za-z -]{0,40}?)(?=\s+(?:PAYMENT|ADJUST|CONTRACTUAL|CLAIM)|$)",
        flat,
        flags=re.I,
    )
    if match is None:
        wrapped = re.search(
            r"(?:^|\s)/\s*([A-Za-z][A-Za-z &.'-]{1,80}?)"
            r"(?=\s+(?:PAYMENT|ADJUST|CONTRACTUAL|CLAIM|Page\s+\d+)|$)",
            flat,
            flags=re.I,
        )
        if wrapped:
            return _clean_payer(wrapped.group(1))
        if continuation:
            return _clean_payer(continuation.group(1))
        if _insurance_payment_label(block):
            return "Insurance Payment"
        return None
    candidate = match.group(1)
    candidate = re.split(
        rf"\b\d{{5,}}\s+{CODE_RE}\s+{DATE_RE}\s+",
        candidate,
        maxsplit=1,
    )[0]
    words = candidate.split()
    while len(words) >= 2 and words[-1].isupper() and words[-2].isupper():
        words = words[:-2]
    candidate = " ".join(words)
    clean_candidate = _clean_payer(candidate)
    if continuation:
        tail = continuation.group(1).strip()
        if not clean_candidate:
            candidate = tail
        elif tail and not re.search(rf"\b{re.escape(tail)}$", candidate, flags=re.I):
            candidate = f"{candidate} {tail}"
    return _clean_payer(candidate)


def _claim_column_payer(lines: list[str], row_index: int) -> str | None:
    before = _claim_column_fragment(lines[max(0, row_index - 3) : row_index], "before")
    after = _claim_column_fragment(lines[row_index + 1 : min(len(lines), row_index + 4)], "after")
    parts = [part for part in (before, after) if part]
    if not parts:
        return None
    if len(parts) == 2 and parts[0].casefold() == parts[1].casefold():
        parts = [parts[0]]
    return _clean_payer(" ".join(parts))


def _claim_column_fragment(lines: list[str], direction: str) -> str | None:
    iterable = reversed(lines) if direction == "before" else iter(lines)
    for line in iterable:
        stripped = line.strip()
        if not stripped or re.search(rf"{DATE_RE}|{MONEY_RE}", stripped):
            continue
        if re.match(r"(?i)^(PAYMENT|ADJUST|CONTRACTUAL|Claim Total|CLAIM TOTAL|\()", stripped):
            continue

        without_provider = re.sub(
            r"\s+[A-Z][A-Z'-]+(?:\s+[A-Z][A-Z'-]+)?$",
            "",
            stripped,
        ).strip()
        if without_provider != stripped:
            fragment = _last_title_fragment(without_provider)
            if fragment:
                return fragment

        if re.search(r"\b[a-z]+\b", stripped) and re.search(r"\b[A-Z][a-z]{2,}\b$", stripped):
            fragment = _last_title_fragment(stripped)
            if fragment:
                return fragment
    return None


def _last_title_fragment(value: str) -> str | None:
    matches = re.findall(r"\b[A-Z][A-Za-z&.'-]{2,}(?:\s+[A-Z][A-Za-z&.'-]{2,})*\b", value)
    return matches[-1] if matches else None


def _continued_diagnosis(segment: str, first_line: str) -> str:
    lines = segment.splitlines()
    if not lines:
        return first_line.strip()
    diagnosis = first_line.strip()
    for line in lines[1:4]:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"(?i)^(Rev|Date|Code|Payment Summary|Total Charges)\b", stripped):
            break
        diagnosis = f"{diagnosis} {stripped}"
        break
    return diagnosis


def _pharmacy_billing_text(text: str) -> str:
    starts = [
        index
        for marker in (
            "RX # FILL DATE",
            "Rx # Date",
            "Date Rx #",
            "Prescription Fill History",
        )
        if (index := text.find(marker)) >= 0
    ]
    if not starts:
        return text
    start = min(starts)
    end_markers = [
        index
        for marker in ("*** END OF PATIENT PROFILE", "Payment Summary", "Total fills:")
        if (index := text.find(marker, start)) >= 0
    ]
    end = min(end_markers) if end_markers else len(text)
    return text[start:end]


def _pharmacy_summary(text: str) -> tuple[float, float | None, float | None, float] | None:
    totals = re.search(
        rf"(?im)^\s*TOTALS?:\s*{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}\s*$",
        text,
    ) or re.search(rf"(?im)^\s*TOTAL\s+{MONEY_RE}\s+{MONEY_RE}\s+{MONEY_RE}\s*$", text)
    if totals:
        return (
            _money_from_match(totals, 1),
            _money_from_match(totals, 2),
            None,
            _money_from_match(totals, 3),
        )

    payment_summary = re.search(
        rf"Payment Summary\s+Patient Paid\s*{MONEY_RE}\s+Insurance Paid\s*{MONEY_RE}\s+"
        rf"Others \(Third Parties\)\s*{MONEY_RE}\s+Grand Total\s*{MONEY_RE}",
        text,
        flags=re.I,
    )
    if payment_summary:
        return (
            _money_from_match(payment_summary, 4),
            _money_from_match(payment_summary, 2),
            _money_from_match(payment_summary, 3),
            _money_from_match(payment_summary, 1),
        )
    return None


def _third_parties(text: str) -> list[str]:
    billing_text = _pharmacy_billing_text(text)
    detail_names = _third_party_detail_names(text)
    if detail_names:
        return detail_names

    prescriber_tokens = _pharmacy_prescriber_tokens(billing_text)
    drug_words = _pharmacy_drug_words(billing_text)
    normalized_candidates: list[str] = []
    candidates = (
        _third_party_candidates_from_bin_markers(
            billing_text,
            prescriber_tokens=prescriber_tokens,
            drug_words=drug_words,
        )
        + _third_party_candidates_from_party_column(
            billing_text,
            prescriber_tokens=prescriber_tokens,
            drug_words=drug_words,
        )
    )
    for name in candidates:
        normalized = _normalize_party_name(
            name,
            prescriber_tokens=prescriber_tokens,
            drug_words=drug_words,
        )
        if normalized:
            normalized_candidates.append(normalized)

    counts = Counter(normalized_candidates)
    min_count = (
        max(3, int(len(normalized_candidates) * 0.03))
        if len(normalized_candidates) >= 50
        else 1
    )
    seen: set[str] = set()
    names: list[str] = []
    for normalized in normalized_candidates:
        if counts[normalized] < min_count:
            continue
        if normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            names.append(normalized)
    return _compact_party_names(names)


def _third_party_detail_names(text: str) -> list[str]:
    match = re.search(
        r"(?is)Third[- ]Party Payer Detail\s+.*?(?=Payment Summary|Grand Total|Page\s+\d+|$)",
        text,
    )
    if match is None:
        return []

    seen: set[str] = set()
    names: list[str] = []
    for raw_line in match.group(0).splitlines():
        line = " ".join(raw_line.split())
        if not line or re.search(r"(?i)^(Third[- ]Party|Payer(?: Name)?\b)", line):
            continue
        if not re.search(MONEY_RE, line):
            continue
        name = re.split(r"\s+BIN\s+\S+|\s+\$", line, maxsplit=1, flags=re.I)[0]
        normalized = _normalize_party_name(name)
        if normalized and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            names.append(normalized)
    return names


def _third_party_candidates_from_bin_markers(
    text: str,
    *,
    prescriber_tokens: set[str],
    drug_words: set[str],
) -> list[str]:
    candidates: list[str] = []
    lines = text.splitlines()
    previous_marker_index = -1
    for index, line in enumerate(lines):
        if not re.search(r"\(BIN\b", line, flags=re.I):
            continue
        parts: list[str] = []
        window_start = max(previous_marker_index + 1, index - 4, 0)
        for raw_line in lines[window_start : index + 1]:
            fragment_line = re.sub(r"\(BIN\b.*$", "", raw_line, flags=re.I)
            fragment = _party_fragment(
                fragment_line,
                prescriber_tokens=prescriber_tokens,
                drug_words=drug_words,
            )
            if fragment:
                parts.append(fragment)
        candidate = " ".join(parts)
        if candidate:
            candidates.append(candidate)
        previous_marker_index = index
    return candidates


def _pharmacy_prescriber_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.fullmatch(r"[A-Z][A-Z'-]{3,}", line):
            tokens.add(line)
        for match in re.finditer(
            rf"\b\d{{5}}-\d{{4}}-\d{{2}}\b\s+(.*?)\s+\d+\s+\d+\s+{MONEY_RE}",
            line,
        ):
            words = match.group(1).split()
            if len(words) >= 2 and words[-1].isupper() and words[-2].isupper():
                tokens.update(words[-2:])
    return tokens


def _pharmacy_drug_words(text: str) -> set[str]:
    words: set[str] = set()
    for match in re.finditer(rf"{DATE_RE}\s+(.+?)\s+\d{{5}}-\d{{4}}-\d{{2}}\b", text):
        for word in re.findall(r"[A-Za-z]+", match.group(1)):
            if len(word) > 1:
                words.add(word.casefold())
    same_line_space = r"[^\S\r\n]+"
    optional_same_line_space = r"[^\S\r\n]*"
    strength_pattern = (
        rf"\b([A-Za-z][A-Za-z-]*){same_line_space}\d+(?:\.\d+)?"
        rf"{optional_same_line_space}(?:mg|mcg|u/mL|mL)\b"
    )
    for match in re.finditer(
        strength_pattern,
        text,
        flags=re.I,
    ):
        words.add(match.group(1).casefold())
    words.update({"inhaler", "refill"})
    return words


def _party_name_from_bin_segment(segment: str, prescriber_tokens: set[str]) -> str | None:
    parts: list[str] = []
    drug_words = _pharmacy_drug_words(segment)
    for raw_line in segment.splitlines():
        line = raw_line.strip()
        if not line or re.search(r"(?i)^(RX #|Date Rx #|Page\s+\d+|TOTALS?:)", line):
            continue
        line = re.sub(r"\(BIN\b.*$", "", line, flags=re.I)
        if re.search(rf"\b{DATE_RE}\b", line) and re.search(r"\b\d{5}-\d{4}-\d{2}\b", line):
            line = re.sub(r"^.*?\b\d{5}-\d{4}-\d{2}\b", "", line)
        if re.search(r"\b\d+\s*(?:mg|mcg|u/mL|mL)\b", line, flags=re.I):
            line = ""
        line = _party_fragment(
            line,
            prescriber_tokens=prescriber_tokens,
            drug_words=drug_words,
        )
        if line:
            parts.append(line)
    return " ".join(parts) if parts else None


def _third_party_candidates_from_party_column(
    text: str,
    *,
    prescriber_tokens: set[str],
    drug_words: set[str],
) -> list[str]:
    if not re.search(r"(?i)3rd Party\s+Prescriber", text):
        return []

    candidates: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        row = " ".join(line.split())
        if not re.search(rf"\b\d{{7}}\s+{DATE_RE}\b", row):
            continue
        ndc = re.search(r"\b\d{5}-\d{4}-\d{2}\b", row)
        if ndc is None:
            continue
        tail = row[ndc.end() :].strip()
        match = re.match(
            rf"(?:(?P<party>.*?)\s+)?[A-Z][A-Z'-]+\s+[A-Z][A-Z'-]+\s+\d+\s+\d+\s+{MONEY_RE}\s+{MONEY_RE}",
            tail,
        )
        body = _party_fragment(
            match.group("party") if match and match.group("party") else "",
            prescriber_tokens=prescriber_tokens,
            drug_words=drug_words,
        )
        if body:
            candidate = body
        else:
            before = _adjacent_party_fragment(
                lines[index - 1] if index > 0 else "",
                prescriber_tokens=prescriber_tokens,
                drug_words=drug_words,
            )
            after = _adjacent_party_fragment(
                lines[index + 1] if index + 1 < len(lines) else "",
                prescriber_tokens=prescriber_tokens,
                drug_words=drug_words,
            )
            candidate = " ".join(part for part in (before, after) if part)
        if candidate:
            candidates.append(candidate)
    return candidates


def _adjacent_party_fragment(
    line: str,
    *,
    prescriber_tokens: set[str],
    drug_words: set[str],
) -> str:
    return _party_fragment(
        line,
        prescriber_tokens=prescriber_tokens,
        drug_words=drug_words,
    ) or ""


def _strip_pharmacy_noise(line: str, prescriber_tokens: set[str]) -> str:
    drug_words = _pharmacy_drug_words(line)
    return _party_fragment(
        line,
        prescriber_tokens=prescriber_tokens,
        drug_words=drug_words,
    ) or ""


def _party_fragment(
    line: str,
    *,
    prescriber_tokens: set[str],
    drug_words: set[str],
) -> str | None:
    if re.search(r"(?i)^\s*(?:RX #|Rx #|Date Rx #|Page\s+\d+|TOTALS?:|TOTAL\b)", line):
        return None
    line = re.sub(r"\([^)]*\)", " ", line)
    line = re.sub(r"\b[A-Z][A-Z'-]+\s+[A-Z][A-Z'-]+\s+\d+\s+\d+\s+", " ", line)
    line = re.sub(rf"{DATE_RE}|\b\d{{7}}\b|\b\d{{5}}-\d{{4}}-\d{{2}}\b|{MONEY_RE}", " ", line)
    line = re.sub(r"\b\d+(?:\.\d+)?(?:mg|mcg|u/mL|mL)?\b", " ", line, flags=re.I)
    line = re.sub(r"\b(?:mg|mcg|u/mL|mL)\b", " ", line, flags=re.I)
    tokens: list[str] = []
    for raw_token in line.split():
        token = raw_token.strip(" ,.;:()")
        if not token:
            continue
        bare = token.strip("-")
        if not bare:
            continue
        if bare.upper() in prescriber_tokens:
            continue
        if bare.casefold() in drug_words:
            continue
        if re.search(r"\d", bare):
            continue
        tokens.append(bare)
    value = " ".join(tokens)
    return value or None


def _tail_name_before_bin(text: str) -> str | None:
    normalized = " ".join(text.replace("—", " ").split())
    if not normalized:
        return None
    normalized = re.sub(r".*\$\d[\d,]*\.\d{2}\s*", "", normalized)
    return normalized


def _normalize_party_name(
    value: str,
    *,
    prescriber_tokens: set[str] | None = None,
    drug_words: set[str] | None = None,
) -> str | None:
    prescriber_tokens = prescriber_tokens or set()
    drug_words = drug_words or set()
    value = " ".join(value.strip().split())
    value = re.sub(r"\s+\([A-Z0-9 -]+\)", "", value)
    value = re.sub(r"\s+[A-Z0-9]+\)$", "", value)
    value = value.strip(" :-—|,.;")
    value = _party_fragment(
        value,
        prescriber_tokens=prescriber_tokens,
        drug_words=drug_words,
    ) or ""
    if not value or re.fullmatch(r"[A-Z]{2,}", value):
        return value if value and len(value) <= 5 else None
    if re.search(r"\d", value):
        return None
    words = value.split()
    if not words or len(words) > 5:
        return None
    return value


def _compact_party_names(names: list[str]) -> list[str]:
    name_set = {name.casefold(): name for name in names}
    compacted: list[str] = []
    for name in names:
        name_key = name.casefold()
        if _is_redundant_party_fragment(name, name_set):
            continue
        if name_key not in {existing.casefold() for existing in compacted}:
            compacted.append(name)
    return compacted


def _is_redundant_party_fragment(name: str, name_set: dict[str, str]) -> bool:
    key = name.casefold()
    words = name.split()
    if len(words) == 1:
        return any(
            other != key and re.search(rf"\b{re.escape(key)}\b", other)
            for other in name_set
        )
    if len(words) == 2 and words[-1].casefold() in {"health", "party"}:
        return any(other != key and other.startswith(key + " ") for other in name_set)
    return False


def _label_money(text: str, label: str) -> float | None:
    match = re.search(rf"(?i){label}\s*{MONEY_RE}", text)
    return _money_from_match(match, 1) if match else None
