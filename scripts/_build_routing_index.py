#!/usr/bin/env python3
"""
Layer-2 routing index for the hybrid hierarchical compliance flow.

Derived from output/openzrplus_dataset.json (the canonical, schema-validated
source of truth). Implements the hybrid hierarchy from the design:

  - Identity spine: media_interface_id -> {format, modulation, symbol_rate,
    power_class, add_drop, designation_type} fixes the mode.
  - Grid is a PARALLEL runtime axis: grid-scoped leaves are bucketed under
    grid_scoped["75"] / grid_scoped["100"] and selected at check time.

Each leaf carries the metadata the engine needs to route + gate:
  evaluator (numeric_range/enum_match/mask/exact/cross_param), severity,
  min/max, unit, aliases, conditional_on, mask_profile_ref, reference.

This is a derived build artifact; its shape differs from
openzrplus.schema.json and is intentionally not validated against it.

Run: python scripts/_build_routing_index.py
"""

import re
import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "openzrplus_dataset.json"
OUT = ROOT / "output" / "openzrplus_routing_index.json"

DIMS = ["format", "symbol_rate_G", "modulation", "power_class", "add_drop", "grid_GHz"]

MASK_BY_NAME = {
    "Laser frequency noise": "mask.laser_freq_noise.60",
    "Tx clock low-frequency phase noise": "mask.tx_clock_phase_noise.60",
    "Tx spectral upper mask": "mask.tx_spectral.upper.60",
    "Tx spectral lower mask": "mask.tx_spectral.lower.60",
}

DESIGNATION_LEGEND = {
    "60LA": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "low",  "add_drop": "colored",   "formally_defined": True},
    "60HA": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": True},
    "60HB": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": True},
    "80HA": {"symbol_rate_GBd_nominal": 80, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": True},
    "80HB": {"symbol_rate_GBd_nominal": 80, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": True},
    "30LA": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "low",  "add_drop": "colored",   "formally_defined": False},
    "30HA": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": False},
    "30HB": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": False},
}


def nominal_rate(sr: float) -> int:
    return int(round(sr))


def designation(power_class: str, sr_nom: int) -> str:
    return f"{sr_nom}{ {'baseline': 'LA', 'HA': 'HA', 'HB': 'HB'}[power_class] }"


def supported_grids(sr_nom: int) -> list:
    return [100] if sr_nom == 80 else [75, 100]


def matches_nongrid(applies_to: dict, prof: dict) -> bool:
    a = applies_to or {}
    fmt = a.get("format")
    if fmt and "ALL" not in fmt and prof["format"] not in fmt:
        return False
    if "symbol_rate_G" in a and prof["symbol_rate_G_nominal"] not in a["symbol_rate_G"]:
        return False
    if "modulation" in a and prof["modulation"] not in a["modulation"]:
        return False
    if "power_class" in a and prof["power_class"] not in a["power_class"]:
        return False
    if "add_drop" in a and prof["add_drop"] not in a["add_drop"]:
        return False
    return True


def specificity(applies_to: dict) -> int:
    a = applies_to or {}
    return sum(1 for k in DIMS if k in a and a[k] != ["ALL"])


def base_name(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def evaluator_for(check_type: str) -> str:
    return {"mask": "mask", "enum_match": "enum_match", "exact": "exact",
            "cross_param": "cross_param"}.get(check_type, "numeric_range")


def to_leaf(p: dict) -> dict:
    leaf = {
        "source_id": p["id"],
        "name": p["name"],
        "base_name": base_name(p["name"]),
        "specificity": specificity(p.get("applies_to", {})),
        "unit": p["unit"],
        "severity": p.get("severity", "mandatory"),
        "evaluator": evaluator_for(p.get("check_type", "range")),
        "check_type": p.get("check_type", "range"),
        "reference": p.get("reference"),
    }
    if "min" in p:
        leaf["min"] = p["min"]
    if "max" in p:
        leaf["max"] = p["max"]
    if "typical" in p:
        leaf["typical"] = p["typical"]
    grid = (p.get("applies_to") or {}).get("grid_GHz")
    if grid:
        leaf["grid_GHz"] = grid
    if p.get("aliases"):
        leaf["aliases"] = p["aliases"]
    if p.get("footnotes"):
        leaf["footnotes"] = p["footnotes"]
    if p.get("test_conditions"):
        leaf["test_conditions"] = p["test_conditions"]
    if p.get("conditional_on"):
        leaf["conditional_on"] = p["conditional_on"]
    if p.get("check_type") == "mask":
        leaf["mask_profile_ref"] = MASK_BY_NAME.get(p["name"])
    if p.get("extraction_notes"):
        leaf["notes"] = p["extraction_notes"]
    return leaf


def dedup_by_specificity(params: list) -> list:
    """Among params sharing a base name, keep only the most specific."""
    groups: dict = {}
    for p in params:
        groups.setdefault(base_name(p["name"]), []).append(p)
    out = []
    for grp in groups.values():
        top = max(specificity(p.get("applies_to", {})) for p in grp)
        out.extend(p for p in grp if specificity(p.get("applies_to", {})) == top)
    return out


def resolve_category(params: list, prof: dict, grid: int | None) -> list:
    """grid=None -> identity-scoped (no grid_GHz in applies_to).
       grid=value -> grid-scoped leaves whose grid_GHz includes that value."""
    sel = []
    for p in params:
        a = p.get("applies_to", {})
        is_grid = "grid_GHz" in a
        if grid is None and is_grid:
            continue
        if grid is not None and not (is_grid and grid in a["grid_GHz"]):
            continue
        if not matches_nongrid(a, prof):
            continue
        sel.append(p)
    sel = dedup_by_specificity(sel)
    return sorted((to_leaf(p) for p in sel), key=lambda e: e["source_id"])


def to_rule(r: dict) -> dict:
    out = {k: r[k] for k in ("rule_id", "group", "predicate_type", "severity", "reference")
           if k in r}
    for k in ("statement", "parameter_ref", "expected_value", "tolerance",
              "tolerance_unit", "rag_fallback"):
        if k in r and r[k] is not None:
            out[k] = r[k]
    return out


def main():
    ds = json.loads(SRC.read_text(encoding="utf-8"))
    opt = ds["optical_specs"]
    tx, rx = opt["tx_optical"], opt["rx_optical"]
    dwdm_norm = [p for p in opt["dwdm_link"] if p["category"] != "filter"]
    dwdm_filt = [p for p in opt["dwdm_link"] if p["category"] == "filter"]

    # Semantic (non per-parameter) rules only; per-param R-<cat>.N rules are
    # represented by the leaves themselves and evaluated there.
    semantic_rules = [r for r in ds["compliance_rules"] if not r["rule_id"].startswith("R-")]

    index = {}
    for i in ds["identity"]:
        mid = i["media_interface_id"]
        sr_nom = nominal_rate(i["symbol_rate_GBd"])
        prof = {
            "format": i["format"], "modulation": i["modulation"],
            "power_class": i["power_class"], "add_drop": i["add_drop_type"],
            "symbol_rate_G_nominal": sr_nom,
        }
        grids = supported_grids(sr_nom)
        grid_scoped = {}
        for g in grids:
            grid_scoped[str(g)] = {
                "dwdm_link": resolve_category(dwdm_norm, prof, g),
                "tx_optical": resolve_category(tx, prof, g),
                "rx_optical": resolve_category(rx, prof, g),
            }
        scoped_rules = [to_rule(r) for r in semantic_rules
                        if matches_nongrid(r.get("applies_to", {}), prof)]
        index[mid] = {
            "identity": {
                "media_interface_id": mid,
                "format": i["format"],
                "line_rate_G": i["payload_rate_G"],
                "modulation": i["modulation"],
                "symbol_rate_GBd": i["symbol_rate_GBd"],
                "symbol_rate_G_nominal": sr_nom,
                "power_class": i["power_class"],
                "add_drop": i["add_drop_type"],
                "designation_type": designation(i["power_class"], sr_nom),
                "sff8024_id_decimal": i.get("sff8024_id_decimal"),
                "sff8024_id_hex": i.get("sff8024_id_hex"),
                "ncg_dB": i.get("ncg_dB"),
                "pre_fec_ber": i.get("pre_fec_ber"),
            },
            "supported_grids_GHz": grids,
            "checks": {
                "identity_scoped": {
                    "dwdm_link": resolve_category(dwdm_norm, prof, None),
                    "tx_optical": resolve_category(tx, prof, None),
                    "rx_optical": resolve_category(rx, prof, None),
                },
                "grid_scoped": grid_scoped,
            },
            "rules": scoped_rules,
        }

    out_doc = {
        "view": "routing_index",
        "description": "Layer-2 hybrid routing index. Identity spine fixes the mode; "
                       "grid is a parallel runtime axis (checks.grid_scoped['75'|'100']). "
                       "Leaves carry evaluator + severity for engine routing/gating.",
        "derived_from": "output/openzrplus_dataset.json",
        "schema_note": "Derived build artifact; shape differs from openzrplus.schema.json (not validated against it).",
        "generated": str(date.today()),
        "meta": {k: ds["meta"][k] for k in ("standard_name", "version", "revision_date",
                                            "source_url", "dataset_version", "extraction_status")},
        "designation_types": DESIGNATION_LEGEND,
        "grids_GHz": [75, 100],
        "shared": {
            "mask_profiles": {m["mask_id"]: m for m in opt["mask_profiles"]},
            "mux_demux_filter_example_75GHz": [to_leaf(p) for p in dwdm_filt],
        },
        "index": index,
    }
    OUT.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"indexed media_interface_ids: {len(index)}")
    for mid in ("ZR400-OFEC-16QAM", "ZR400-OFEC-8QAM-HA", "ZR300-OFEC-8QAM"):
        n = index[mid]
        idsc = n["checks"]["identity_scoped"]
        print(f"  {mid} [{n['identity']['designation_type']}] grids={n['supported_grids_GHz']} "
              f"id_tx={len(idsc['tx_optical'])} id_rx={len(idsc['rx_optical'])} "
              f"id_dwdm={len(idsc['dwdm_link'])} rules={len(n['rules'])}")


if __name__ == "__main__":
    main()
