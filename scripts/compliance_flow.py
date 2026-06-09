#!/usr/bin/env python3
"""
OpenZR+ Hierarchical Compliance Engine (hybrid flow)
=====================================================
Walks the Layer-2 routing index (output/openzrplus_routing_index.json) instead
of scanning every parameter. Implements the hybrid design:

  1. Resolve module identity from the index by media_interface_id (real fields,
     never inferred from MID substrings -- this avoids the ZR300-OFEC-8QAM
     "8qam => 80 GBd" mislabel bug in compliance_checker._applies_to_match).
  2. Collect applicable leaves = identity_scoped + grid_scoped[grid] for the
     deployment grid supplied at check time (grid is the parallel axis).
  3. Route each leaf by evaluator: numeric_range | enum_match | mask | exact.
  4. Route semantic rules by predicate_type (prose_rag -> NEEDS_RAG; enum/
     tolerance -> deterministic where vendor data allows).
  5. Severity-gate and aggregate: mandatory/conditional failure -> FAIL,
     recommended -> WARN, informative -> reported only.

This module is additive; it does not modify compliance_checker.py.

Usage:
    python compliance_flow.py --index ../output/openzrplus_routing_index.json \
                              --vendor ../vendor.json [--grid 75|100]

Importable:
    from compliance_flow import check_flow, load_index
"""

import json
import argparse
from pathlib import Path
from enum import Enum


class V(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    NOT_TESTED = "NOT_TESTED"
    NEEDS_RAG = "NEEDS_RAG"
    NEEDS_MASK = "NEEDS_MASK"
    INFO = "INFO"
    INAPPLICABLE = "INAPPLICABLE"


FAIL_SEVERITIES = {"mandatory", "conditional"}   # "SHALL" / "SHALL WHEN" (scope already gates the WHEN)
WARN_SEVERITIES = {"recommended"}


def load_index(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _find_value(names, vendor_params):
    """Match a vendor param key to a leaf's canonical name / aliases (exact, case-insensitive)."""
    cands = {n.lower() for n in names if n}
    for key, val in vendor_params.items():
        if key.lower() in cands:
            return key, val
    return None, None


def _gate(severity: str, in_range: bool) -> V:
    if in_range:
        return V.PASS
    if severity in FAIL_SEVERITIES:
        return V.FAIL
    if severity in WARN_SEVERITIES:
        return V.WARN
    return V.INFO


def _eval_numeric(leaf, vendor_params):
    names = [leaf["name"]] + leaf.get("aliases", [])
    key, raw = _find_value(names, vendor_params)
    lo, hi, unit = leaf.get("min"), leaf.get("max"), leaf.get("unit")
    sev = leaf.get("severity", "mandatory")
    if raw is None:
        return _result(leaf, V.NOT_TESTED, None, "parameter not provided by vendor")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return _result(leaf, V.WARN, raw, f"non-numeric vendor value '{raw}'")
    notes = []
    ok = True
    if lo is not None and v < lo:
        ok = False
        notes.append(f"below minimum {lo} {unit}")
    if hi is not None and v > hi:
        ok = False
        notes.append(f"above maximum {hi} {unit}")
    return _result(leaf, _gate(sev, ok), v, "; ".join(notes))


def _eval_enum(leaf, vendor_params):
    names = [leaf["name"]] + leaf.get("aliases", [])
    key, raw = _find_value(names, vendor_params)
    if raw is None:
        return _result(leaf, V.NOT_TESTED, None, "parameter not provided by vendor")
    exp = leaf.get("expected_value")
    if exp is None:
        return _result(leaf, V.NOT_TESTED, raw, "no expected value defined for enum check")
    ok = str(raw).lower() == str(exp).lower()
    return _result(leaf, _gate(leaf.get("severity", "mandatory"), ok), raw,
                   "" if ok else f"expected '{exp}'")


def _eval_mask(leaf, vendor_params):
    return _result(leaf, V.NEEDS_MASK, None,
                   f"mask check vs {leaf.get('mask_profile_ref')} - requires vendor spectral/noise curve")


def _result(leaf, verdict: V, value, notes: str) -> dict:
    return {
        "source_id": leaf.get("source_id"),
        "param": leaf["name"],
        "verdict": verdict.value,
        "vendor_value": value,
        "limit_min": leaf.get("min"),
        "limit_max": leaf.get("max"),
        "unit": leaf.get("unit"),
        "severity": leaf.get("severity", "mandatory"),
        "evaluator": leaf.get("evaluator"),
        "grid_GHz": leaf.get("grid_GHz"),
        "reference": leaf.get("reference"),
        "notes": notes,
    }


LEAF_EVALUATORS = {
    "numeric_range": _eval_numeric,
    "exact": _eval_numeric,
    "enum_match": _eval_enum,
    "mask": _eval_mask,
}


def _eval_leaf(leaf, vendor_params):
    fn = LEAF_EVALUATORS.get(leaf.get("evaluator"))
    if fn is None:
        return _result(leaf, V.NEEDS_RAG, None, f"evaluator '{leaf.get('evaluator')}' not deterministic")
    return fn(leaf, vendor_params)


def _eval_rule(rule, ident, vendor):
    """Deterministic handling for semantic rules where vendor data allows; else NEEDS_RAG."""
    vp = vendor.get("params", {})
    rid = rule["rule_id"]
    sev = rule.get("severity", "mandatory")

    def res(verdict, value, notes):
        return {"rule_id": rid, "param": rule.get("statement", "")[:70], "verdict": verdict.value,
                "vendor_value": value, "severity": sev, "predicate_type": rule.get("predicate_type"),
                "reference": rule.get("reference"), "notes": notes}

    if rid == "R1.1":  # SFF-8024 media interface ID match
        adv = vendor.get("sff8024_id_hex") or vp.get("sff8024_id_hex")
        exp = ident.get("sff8024_id_hex")
        if adv is None:
            return res(V.NOT_TESTED, None, "vendor did not advertise sff8024_id_hex")
        if exp in (None, "TBD"):
            return res(V.NEEDS_RAG, adv, "spec ID is TBD for this enhanced mode")
        ok = str(adv).lower() == str(exp).lower()
        return res(V.PASS if ok else V.FAIL, adv, "" if ok else f"expected {exp}")

    if rid == "R3.1":  # modulation match
        adv = vendor.get("modulation") or vp.get("modulation")
        exp = ident.get("modulation")
        if adv is None:
            return res(V.NOT_TESTED, None, "vendor did not provide modulation")
        ok = str(adv).lower() == str(exp).lower()
        return res(V.PASS if ok else V.FAIL, adv, "" if ok else f"expected {exp}")

    if rid == "R2.1":  # baud rate within +/- tolerance ppm
        adv = vendor.get("baud_rate_GBd") or vp.get("baud_rate_GBd") or vp.get("symbol_rate_GBd")
        nominal = ident.get("symbol_rate_GBd")
        tol_ppm = rule.get("tolerance", 20)
        if adv is None:
            return res(V.NOT_TESTED, None, "vendor did not provide baud rate")
        dev_ppm = abs(float(adv) - nominal) / nominal * 1e6
        ok = dev_ppm <= tol_ppm
        return res(V.PASS if ok else V.FAIL, adv,
                   f"deviation {dev_ppm:.2f} ppm vs nominal {nominal} GBd (limit {tol_ppm} ppm)")

    if rid == "R4.1":  # OFEC NCG >= 11.6 dB
        adv = vendor.get("ncg_dB") or vp.get("ncg_dB")
        exp = rule.get("expected_value", 11.6)
        if adv is None:
            return res(V.NOT_TESTED, None, "vendor did not provide NCG")
        ok = float(adv) >= float(exp)
        return res(V.PASS if ok else V.FAIL, adv, "" if ok else f"below {exp} dB")

    # table_lookup / cross_param_ratio / prose_rag and anything else -> escalate
    return res(V.NEEDS_RAG, None, "requires RAG/LLM verification against the standard PDF")


def check_flow(vendor: dict, index: dict, grid: int | str | None = None) -> dict:
    mid = vendor["media_interface_id"]
    node = index.get("index", {}).get(mid)
    if node is None:
        return {"media_interface_id": mid, "overall_verdict": "ERROR",
                "error": f"Unknown media_interface_id '{mid}'.",
                "known": list(index.get("index", {}).keys())}

    ident = node["identity"]
    supported = node["supported_grids_GHz"]

    grid = grid if grid is not None else vendor.get("grid_GHz")
    grid_note = None
    if grid is not None:
        grid = int(grid)
        if grid not in supported:
            grid_note = f"requested grid {grid} GHz not in supported {supported}; grid-scoped checks skipped"
            grid = None
    elif len(supported) == 1:
        grid = supported[0]
        grid_note = f"grid not supplied; defaulted to the only supported grid {grid} GHz"
    else:
        grid_note = f"grid not supplied; grid-scoped checks skipped (supported: {supported})"

    vp = vendor.get("params", {})

    # Gather applicable leaves: identity-scoped + grid-scoped (parallel axis).
    leaves = []
    idsc = node["checks"]["identity_scoped"]
    for cat in ("dwdm_link", "tx_optical", "rx_optical"):
        leaves.extend(idsc[cat])
    if grid is not None:
        gsc = node["checks"]["grid_scoped"].get(str(grid), {})
        for cat in ("dwdm_link", "tx_optical", "rx_optical"):
            leaves.extend(gsc.get(cat, []))

    # Cross-bucket dedup: where a generic (grid-agnostic) and a more specific
    # (grid/modulation-scoped) limit share a base name, keep only the most
    # specific (e.g. 400G CD link budget 20000 generic vs 30000 for 8QAM/100 GHz).
    groups = {}
    for leaf in leaves:
        groups.setdefault(leaf.get("base_name", leaf["name"]), []).append(leaf)
    results = []
    for grp in groups.values():
        top = max(l.get("specificity", 0) for l in grp)
        for leaf in grp:
            if leaf.get("specificity", 0) == top:
                results.append(_eval_leaf(leaf, vp))

    # semantic rules
    rule_results = [_eval_rule(r, ident, vendor) for r in node.get("rules", [])]

    # aggregate
    all_verdicts = [r["verdict"] for r in results] + [r["verdict"] for r in rule_results]
    counts = {v.value: 0 for v in V}
    for x in all_verdicts:
        counts[x] = counts.get(x, 0) + 1
    mandatory_fails = [r for r in (results + rule_results)
                       if r["verdict"] == V.FAIL.value and r["severity"] in FAIL_SEVERITIES]
    overall = "FAIL" if mandatory_fails else "PASS"

    return {
        "media_interface_id": mid,
        "overall_verdict": overall,
        "routing_path": {
            "designation_type": ident["designation_type"],
            "format": ident["format"],
            "line_rate_G": ident["line_rate_G"],
            "modulation": ident["modulation"],
            "symbol_rate_GBd": ident["symbol_rate_GBd"],
            "power_class": ident["power_class"],
            "add_drop": ident["add_drop"],
            "grid_GHz": grid,
            "supported_grids_GHz": supported,
            "grid_note": grid_note,
        },
        "summary": {k: counts[k] for k in
                    ("PASS", "FAIL", "WARN", "NOT_TESTED", "NEEDS_RAG", "NEEDS_MASK", "INFO", "INAPPLICABLE")},
        "leaves_evaluated": len(results),
        "rules_evaluated": len(rule_results),
        "mandatory_failures": [
            {"id": r.get("source_id") or r.get("rule_id"), "param": r["param"],
             "vendor_value": r["vendor_value"], "notes": r["notes"]}
            for r in mandatory_fails
        ],
        "results": results,
        "rule_results": rule_results,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="OpenZR+ hierarchical compliance engine")
    ap.add_argument("--index", required=True, help="Path to openzrplus_routing_index.json")
    ap.add_argument("--vendor", required=True, help="Path to normalised vendor datasheet JSON")
    ap.add_argument("--grid", type=int, choices=[75, 100], default=None, help="Deployment grid (GHz)")
    ap.add_argument("--out", default=None, help="Output report path (default: stdout)")
    args = ap.parse_args()

    idx = load_index(Path(args.index))
    vendor = json.loads(Path(args.vendor).read_text(encoding="utf-8-sig"))
    report = check_flow(vendor, idx, grid=args.grid)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Report -> {args.out}")
    else:
        print(text)
