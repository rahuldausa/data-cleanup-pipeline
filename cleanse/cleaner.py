"""
Data cleansing pipeline for raw provider/credential records.
Handles: mixed name formats, invalid NPIs, inconsistent dates,
         mixed state codes, duplicates, and missing fields.
"""

import re
import pandas as pd
from typing import Optional

# ── Lookup tables ──────────────────────────────────────────────────────────────

_STATE_LOOKUP = {
    # Full names
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
    # 2-letter abbreviations (self-mapping)
    "al": "AL", "ak": "AK", "az": "AZ", "ar": "AR", "ca": "CA",
    "co": "CO", "ct": "CT", "de": "DE", "fl": "FL", "ga": "GA",
    "hi": "HI", "id": "ID", "il": "IL", "in": "IN", "ia": "IA",
    "ks": "KS", "ky": "KY", "la": "LA", "me": "ME", "md": "MD",
    "ma": "MA", "mi": "MI", "mn": "MN", "ms": "MS", "mo": "MO",
    "mt": "MT", "ne": "NE", "nv": "NV", "nh": "NH", "nj": "NJ",
    "nm": "NM", "ny": "NY", "nc": "NC", "nd": "ND", "oh": "OH",
    "ok": "OK", "or": "OR", "pa": "PA", "ri": "RI", "sc": "SC",
    "sd": "SD", "tn": "TN", "tx": "TX", "ut": "UT", "vt": "VT",
    "va": "VA", "wa": "WA", "wv": "WV", "wi": "WI", "wy": "WY",
}

_CREDENTIAL_LOOKUP = {
    "medicallicense":       "MedicalLicense",
    "medical license":      "MedicalLicense",
    "boardcertification":   "BoardCertification",
    "board certification":  "BoardCertification",
    "dearegistration":      "DEARegistration",
    "dea registration":     "DEARegistration",
}

_SPECIALTY_LOOKUP = {
    "cardio":           "Cardiology",
    "cardiology":       "Cardiology",
    "oncology":         "Oncology",
    "neurology":        "Neurology",
    "orthopedics":      "Orthopedics",
    "orthopedic":       "Orthopedics",
    "family medicine":  "Family Medicine",
    "pediatrics":       "Pediatrics",
    "psychiatry":       "Psychiatry",
    "radiology":        "Radiology",
    "dermatology":      "Dermatology",
}

_HONORIFICS = re.compile(
    r"\b(dr\.?|md\.?|do\.?|np\.?|pa\.?|phd\.?|dpm\.?)\b",
    flags=re.IGNORECASE,
)

# ── Normalizer helpers ─────────────────────────────────────────────────────────

def _normalize_name(name) -> Optional[str]:
    if name is None or not str(name).strip():
        return None
    s = str(name).strip()
    s = _HONORIFICS.sub("", s)
    s = re.sub(r"^\s*[.,]\s*|\s*[.,]\s*$", "", s).strip()  # remove orphaned punctuation
    s = re.sub(r"\s{2,}", " ", s)
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        s = f"{parts[1]} {parts[0]}"
    s = s.title().strip()
    return s if s else None


def _validate_npi(npi) -> Optional[str]:
    if npi is None:
        return None
    digits = re.sub(r"\D", "", str(npi))
    if len(digits) != 10:
        return None
    if len(set(digits)) == 1:          # e.g., "0000000000"
        return None
    return digits


def _parse_date(date_str) -> pd.Timestamp:
    if date_str is None or not str(date_str).strip():
        return pd.NaT
    s = str(date_str).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d %Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            pass
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return pd.NaT


def _normalize_state(state) -> Optional[str]:
    if state is None or not str(state).strip():
        return None
    key = str(state).strip().lower()
    return _STATE_LOOKUP.get(key)


def _normalize_credential_type(ct) -> Optional[str]:
    if ct is None:
        return None
    key = str(ct).strip().lower()
    result = _CREDENTIAL_LOOKUP.get(key)
    if result:
        return result
    return _CREDENTIAL_LOOKUP.get(key.replace(" ", ""))


def _normalize_specialty(spec) -> Optional[str]:
    if spec is None or not str(spec).strip():
        return None
    key = str(spec).strip().lower()
    return _SPECIALTY_LOOKUP.get(key, str(spec).title())


def _normalize_organization(org) -> Optional[str]:
    if org is None:
        return None
    s = str(org).strip()
    if s.lower() in ("n/a", "na", "none", ""):
        return None
    return s


def _normalize_license_number(lic) -> Optional[str]:
    if lic is None:
        return None
    s = str(lic).strip()
    return s if s else None

# ── Per-field cleansing rules (label, normalizer, formatter) ──────────────────

def _fmt_date(val) -> str:
    """Format a parsed date for display, or return the raw string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "None"
    try:
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    except Exception:
        return str(val)


_FIELD_RULES = [
    # (field, normalizer_fn, display_formatter, rule_description)
    ("name",            _normalize_name,            str,       "strip honorifics, fix LAST,FIRST order, title-case"),
    ("npi",             _validate_npi,              str,       "must be 10 digits, no all-same-digit"),
    ("license_expiry",  _parse_date,                _fmt_date, "parse multiple date formats"),
    ("state",           _normalize_state,           str,       "map full name / casing to 2-letter code"),
    ("credential_type", _normalize_credential_type, str,       "normalise casing to canonical type"),
    ("specialty",       _normalize_specialty,       str,       "expand abbreviations, title-case"),
    ("organization",    _normalize_organization,    str,       "strip whitespace, nullify sentinels (N/A)"),
    ("license_number",  _normalize_license_number,  str,       "strip whitespace"),
]


def cleansing_report(raw_records: list) -> list:
    """
    Return a per-record report of what changed during cleansing.

    Each entry:
        {
            "index":   int,
            "status":  "cleaned" | "duplicate" | "unchanged",
            "changes": [{"field", "before", "after", "rule"}],
        }
    """
    # First pass: apply normalizers and detect changes
    reports = []
    for i, rec in enumerate(raw_records):
        changes = []
        for field, fn, fmt, rule in _FIELD_RULES:
            raw_val = rec.get(field)
            clean_val = fn(raw_val)

            raw_str   = fmt(raw_val)   if raw_val   is not None else "None"
            clean_str = fmt(clean_val) if clean_val is not None else "None"

            # Normalise both for comparison (strip, lower) to avoid trivial whitespace diffs
            if str(raw_str).strip() != str(clean_str).strip():
                changes.append({
                    "field":  field,
                    "before": raw_str,
                    "after":  clean_str,
                    "rule":   rule,
                })

        reports.append({
            "index":   i,
            "name":    rec.get("name", ""),
            "npi":     rec.get("npi", ""),
            "status":  "unchanged" if not changes else "cleaned",
            "changes": changes,
        })

    # Second pass: mark duplicates
    # A record is a near-duplicate if same NPI appeared in an earlier record
    seen_npis: dict = {}
    for rep in reports:
        raw_npi = rep["npi"]
        clean_npi = _validate_npi(raw_npi)
        if clean_npi:
            if clean_npi in seen_npis:
                rep["status"] = "duplicate"
                rep["duplicate_of"] = seen_npis[clean_npi]
            else:
                seen_npis[clean_npi] = rep["index"]

    return reports


# ── Main pipeline ──────────────────────────────────────────────────────────────

def clean_providers(raw_records: list) -> tuple:
    """
    Cleanse a list of raw provider dicts.

    Returns:
        (clean_df, stats_dict)
    """
    df = pd.DataFrame(raw_records)

    stats = {
        "total_raw": len(df),
        "null_counts_before": df.isnull().sum().to_dict(),
    }

    # Apply normalizations
    df["name"]            = df["name"].apply(_normalize_name)
    df["state"]           = df["state"].apply(_normalize_state)
    df["specialty"]       = df["specialty"].apply(_normalize_specialty)
    df["organization"]    = df["organization"].apply(_normalize_organization)
    df["credential_type"] = df["credential_type"].apply(_normalize_credential_type)
    df["license_number"]  = df["license_number"].apply(_normalize_license_number)

    npi_null_before = int(df["npi"].isnull().sum())
    df["npi"] = df["npi"].apply(_validate_npi)
    stats["invalid_npis_fixed"] = int(df["npi"].isnull().sum()) - npi_null_before

    date_null_before = int(df["license_expiry"].isnull().sum())
    df["license_expiry"] = df["license_expiry"].apply(_parse_date)
    dates_now_null = int(df["license_expiry"].isna().sum())
    stats["dates_parsed"] = max(0, date_null_before - dates_now_null)

    # Drop exact duplicates
    before_dedup = len(df)
    df = df.drop_duplicates()

    # Resolve near-duplicates by NPI: keep the most complete row per NPI
    npi_valid = df.dropna(subset=["npi"])
    npi_null  = df[df["npi"].isna()]
    deduped_rows = []
    for _npi, group in npi_valid.groupby("npi"):
        scores = group.notna().sum(axis=1)
        deduped_rows.append(group.loc[[scores.idxmax()]])
    deduped = pd.concat(deduped_rows, ignore_index=True) if deduped_rows else pd.DataFrame(columns=df.columns)
    df = pd.concat([deduped, npi_null], ignore_index=True)

    stats["duplicates_removed"]  = before_dedup - len(df)
    stats["total_clean"]         = len(df)
    stats["null_counts_after"]   = df.isnull().sum().to_dict()

    return df, stats
