#!/usr/bin/env python3
"""
OpenZR+ Compliance Checker
============================
Checks a normalised vendor datasheet dict against the frozen OpenZR+ dataset.

Usage:
    python compliance_checker.py --dataset output/openzrplus_dataset.json
                                  --vendor your_vendor_datasheet.json

Vendor datasheet JSON format (minimal required fields):
{
  "media_interface_id": "ZR400-OFEC-16QAM-HA",
  "params": {
    "tx_output_power_dBm":   2.0,
    "rx_input_power_min_dBm": -18.0,
    "channel_frequency_THz": 193.1,
    ...
  }
}

Cursor: Import check_compliance() for use in a larger qualification workflow.
"""

import json
import math
import logging
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class Verdict(str, Enum):
    PASS         = "PASS"
    FAIL         = "FAIL"
    WARN         = "WARN"          # Recommended param out of range
    NOT_TESTED   = "NOT_TESTED"    # Param not present in vendor datasheet
    NEEDS_RAG    = "NEEDS_RAG"     # prose_rag rule — needs LLM over PDF
    INAPPLICABLE = "INAPPLICABLE"  # Rule doesn't apply to this media_interface_id


@dataclass
class CheckResult:
    rule_id:         str
    param_name:      str
    verdict:         Verdict
    vendor_value:    float | str | None
    limit_min:       float | None
    limit_max:       float | None
    unit:            str | None
    severity:        str
    notes:           str = ""
    cross_refs:      list = field(default_factory=list)


def load_dataset(path: Path) -> dict:
    return json.loads(path.read_text())


def _applies_to_match(applies_to_filter: dict, media_interface_id: str) -> bool:
    """
    Check if a parameter's applies_to filter includes the given media_interface_id.
    Structured filter is checked against known properties of the MID string.
    """
    if not applies_to_filter:
        return True  # No filter = applies to all

    mid = media_interface_id.lower()

    # format check
    formats = applies_to_filter.get("format", [])
    if formats:
        format_match = any(f.replace("+", "").lower() in mid for f in formats if f != "ALL")
        if formats and "ALL" not in formats and not format_match:
            return False

    # symbol_rate check
    rates = applies_to_filter.get("symbol_rate_G", [])
    if rates:
        # infer symbol rate from MID name
        if "8qam" in mid:  # 80G modes
            inferred_rate = 80
        elif "100zr" in mid:
            inferred_rate = 30
        else:
            inferred_rate = 60
        if inferred_rate not in rates:
            return False

    # power_class check
    power_classes = applies_to_filter.get("power_class", [])
    if power_classes:
        if "ha" in mid and "HA" not in power_classes:
            return False
        if "hb" in mid and "HB" not in power_classes:
            return False
        if "ha" not in mid and "hb" not in mid and "baseline" not in power_classes:
            return False

    # add_drop check
    add_drop = applies_to_filter.get("add_drop", [])
    if add_drop:
        if "hb" in mid and "colorless" not in add_drop:
            return False
        if "hb" not in mid and "colored" not in add_drop:
            return False

    return True


def _find_applicable_params(dataset: dict, category: str,
                              media_interface_id: str) -> list[dict]:
    """Return all params in a category that apply to the given MID."""
    section_map = {
        "dwdm_link":  dataset.get("optical_specs", {}).get("dwdm_link", []),
        "tx_optical": dataset.get("optical_specs", {}).get("tx_optical", []),
        "rx_optical": dataset.get("optical_specs", {}).get("rx_optical", []),
    }
    params = section_map.get(category, [])
    return [p for p in params
            if _applies_to_match(p.get("applies_to", {}), media_interface_id)]


def check_numeric_range(param: dict, vendor_params: dict,
                         media_interface_id: str) -> CheckResult:
    """Check a numeric_range or numeric_tolerance param against vendor value."""
    pid     = param["id"]
    name    = param["name"]
    unit    = param.get("unit")
    severity = param.get("severity", "mandatory")
    aliases = [name.lower()] + [a.lower() for a in param.get("aliases", [])]
    cross_refs = param.get("cross_standard_refs", [])

    # Find vendor value — try canonical name and aliases
    vendor_value = None
    for key in vendor_params:
        if key.lower() in aliases or any(a in key.lower() for a in aliases):
            vendor_value = vendor_params[key]
            break

    if vendor_value is None:
        return CheckResult(
            rule_id=pid, param_name=name,
            verdict=Verdict.NOT_TESTED,
            vendor_value=None,
            limit_min=param.get("min"), limit_max=param.get("max"),
            unit=unit, severity=severity,
            notes="Parameter not found in vendor datasheet",
            cross_refs=cross_refs,
        )

    lo = param.get("min")
    hi = param.get("max")

    try:
        v = float(vendor_value)
    except (TypeError, ValueError):
        return CheckResult(
            rule_id=pid, param_name=name,
            verdict=Verdict.WARN,
            vendor_value=vendor_value,
            limit_min=lo, limit_max=hi,
            unit=unit, severity=severity,
            notes=f"Could not convert vendor value '{vendor_value}' to float",
            cross_refs=cross_refs,
        )

    in_range = True
    notes_parts = []
    if lo is not None and v < lo:
        in_range = False
        notes_parts.append(f"below minimum {lo} {unit}")
    if hi is not None and v > hi:
        in_range = False
        notes_parts.append(f"above maximum {hi} {unit}")

    if in_range:
        verdict = Verdict.PASS
    elif severity == "mandatory":
        verdict = Verdict.FAIL
    else:
        verdict = Verdict.WARN

    return CheckResult(
        rule_id=pid, param_name=name,
        verdict=verdict,
        vendor_value=v,
        limit_min=lo, limit_max=hi,
        unit=unit, severity=severity,
        notes="; ".join(notes_parts),
        cross_refs=cross_refs,
    )


def check_compliance(vendor: dict, dataset: dict) -> dict:
    """
    Main entry point. Returns a structured compliance report.

    Args:
        vendor:  Normalised vendor datasheet dict with 'media_interface_id' and 'params'
        dataset: Loaded OpenZR+ dataset JSON

    Returns:
        Compliance report dict with per-param results and summary verdict.
    """
    mid           = vendor["media_interface_id"]
    vendor_params = vendor.get("params", {})
    results       = []

    # ── Verify media_interface_id exists in dataset ──
    known_mids = [i["media_interface_id"] for i in dataset.get("identity", [])]
    if mid not in known_mids:
        return {
            "media_interface_id": mid,
            "verdict": "ERROR",
            "error": f"Unknown media_interface_id '{mid}'. Known: {known_mids}",
        }

    # ── Check all optical params ──
    for category in ["dwdm_link", "tx_optical", "rx_optical"]:
        applicable = _find_applicable_params(dataset, category, mid)
        for param in applicable:
            result = check_numeric_range(param, vendor_params, mid)
            results.append(result)

    # ── Check compliance rules ──
    for rule in dataset.get("compliance_rules", []):
        applies = _applies_to_match(rule.get("applies_to", {}), mid)
        if not applies:
            results.append(CheckResult(
                rule_id=rule["rule_id"], param_name=rule.get("statement", "")[:60],
                verdict=Verdict.INAPPLICABLE,
                vendor_value=None, limit_min=None, limit_max=None,
                unit=None, severity=rule.get("severity", "mandatory"),
                cross_refs=rule.get("cross_standard_refs", []),
            ))
            continue

        pred = rule.get("predicate_type")
        if pred == "prose_rag":
            results.append(CheckResult(
                rule_id=rule["rule_id"], param_name=rule.get("statement", "")[:60],
                verdict=Verdict.NEEDS_RAG,
                vendor_value=None, limit_min=None, limit_max=None,
                unit=None, severity=rule.get("severity", "mandatory"),
                notes="Prose rule — requires LLM verification against standard PDF",
                cross_refs=rule.get("cross_standard_refs", []),
            ))

    # ── Summary ──
    counts = {v: 0 for v in Verdict}
    for r in results:
        counts[r.verdict] += 1

    mandatory_fails = [r for r in results
                       if r.verdict == Verdict.FAIL and r.severity == "mandatory"]

    overall = "PASS" if not mandatory_fails else "FAIL"

    return {
        "media_interface_id": mid,
        "overall_verdict":    overall,
        "summary": {
            "pass":          counts[Verdict.PASS],
            "fail":          counts[Verdict.FAIL],
            "warn":          counts[Verdict.WARN],
            "not_tested":    counts[Verdict.NOT_TESTED],
            "needs_rag":     counts[Verdict.NEEDS_RAG],
            "inapplicable":  counts[Verdict.INAPPLICABLE],
        },
        "mandatory_failures": [
            {
                "rule_id":      r.rule_id,
                "param":        r.param_name,
                "vendor_value": r.vendor_value,
                "limit_min":    r.limit_min,
                "limit_max":    r.limit_max,
                "unit":         r.unit,
                "notes":        r.notes,
            }
            for r in mandatory_fails
        ],
        "results": [
            {
                "rule_id":      r.rule_id,
                "param":        r.param_name,
                "verdict":      r.verdict.value,
                "vendor_value": r.vendor_value,
                "limit_min":    r.limit_min,
                "limit_max":    r.limit_max,
                "unit":         r.unit,
                "severity":     r.severity,
                "notes":        r.notes,
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to openzrplus_dataset.json")
    parser.add_argument("--vendor",  required=True, help="Path to normalised vendor datasheet JSON")
    parser.add_argument("--out",     default=None,  help="Output report path (default: stdout)")
    args = parser.parse_args()

    dataset = load_dataset(Path(args.dataset))
    vendor  = json.loads(Path(args.vendor).read_text())
    report  = check_compliance(vendor, dataset)

    out = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(out)
        log.info(f"Report → {args.out}")
    else:
        print(out)
