#!/usr/bin/env python3
"""
Mode-centric (pivoted) view of OpenZR+ optical_specs.

Reads the parameter-centric dataset (output/openzrplus_dataset.json) and pivots
optical_specs so that limits are grouped by line rate / mode and designation
type (60LA, 60HA, 60HB, 80HA, 80HB, plus the 30 GBd 100ZR+ variants) instead of
by parameter. Each per-parameter `applies_to` filter is resolved into a concrete
value for every mode.

This is a derived convenience view; its shape differs from openzrplus.schema.json
and is intentionally NOT validated against it.

Run: python scripts/_build_mode_view.py
"""

import re
import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "openzrplus_dataset.json"
OUT = ROOT / "output" / "openzrplus_optical_by_mode.json"

DIMS = ["format", "symbol_rate_G", "modulation", "power_class", "add_drop", "grid_GHz"]

DESIGNATION_LEGEND = {
    "60LA": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "low",  "add_drop": "colored",   "formally_defined": True,  "reference": "Table 11-0, §11"},
    "60HA": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": True,  "reference": "Table 11-0, §11"},
    "60HB": {"symbol_rate_GBd_nominal": 60, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": True,  "reference": "Table 11-0, §11"},
    "80HA": {"symbol_rate_GBd_nominal": 80, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": True,  "reference": "Table 11-0, §11"},
    "80HB": {"symbol_rate_GBd_nominal": 80, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": True,  "reference": "Table 11-0, §11"},
    "30LA": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "low",  "add_drop": "colored",   "formally_defined": False, "note": "100ZR+ baseline; Table 11-0 names only the 60/80 GBd designations — 30-prefixed labels are derived for consistency."},
    "30HA": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "high", "add_drop": "colored",   "formally_defined": False, "note": "100ZR+ high-power colored; designation label derived."},
    "30HB": {"symbol_rate_GBd_nominal": 30, "tx_output_power": "high", "add_drop": "colorless", "formally_defined": False, "note": "100ZR+ high-power colorless; designation label derived."},
}
GROUP_ORDER = ["60LA", "60HA", "60HB", "80HA", "80HB", "30LA", "30HA", "30HB"]

MASK_BY_NAME = {
    "Laser frequency noise": "mask.laser_freq_noise.60",
    "Tx clock low-frequency phase noise": "mask.tx_clock_phase_noise.60",
    "Tx spectral upper mask": "mask.tx_spectral.upper.60",
    "Tx spectral lower mask": "mask.tx_spectral.lower.60",
}


def nominal_rate(symbol_rate_GBd: float) -> int:
    return int(round(symbol_rate_GBd))


def designation(power_class: str, sr_nom: int) -> str:
    suffix = {"baseline": "LA", "HA": "HA", "HB": "HB"}[power_class]
    return f"{sr_nom}{suffix}"


def supported_grids(sr_nom: int) -> list:
    return [100] if sr_nom == 80 else [75, 100]


def matches(applies_to: dict, prof: dict) -> bool:
    """Structured match on every dimension except grid (grid handled separately)."""
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
    if "grid_GHz" in a and not (set(a["grid_GHz"]) & set(prof["supported_grids_GHz"])):
        return False
    return True


def specificity(applies_to: dict) -> int:
    a = applies_to or {}
    return sum(1 for k in DIMS if k in a and a[k] != ["ALL"])


def base_name(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def to_entry(p: dict) -> dict:
    e = {"name": p["name"], "source_id": p["id"], "unit": p["unit"],
         "severity": p.get("severity", "mandatory"),
         "check_type": p.get("check_type", "range"),
         "reference": p.get("reference")}
    if "min" in p:
        e["min"] = p["min"]
    if "max" in p:
        e["max"] = p["max"]
    if "typical" in p:
        e["typical"] = p["typical"]
    grid = (p.get("applies_to") or {}).get("grid_GHz")
    if grid:
        e["grid_GHz"] = grid
    if p.get("footnotes"):
        e["footnotes"] = p["footnotes"]
    if p.get("test_conditions"):
        e["test_conditions"] = p["test_conditions"]
    if p.get("aliases"):
        e["aliases"] = p["aliases"]
    if p.get("check_type") == "mask":
        e["mask_profile_ref"] = MASK_BY_NAME.get(p["name"])
    if p.get("extraction_notes"):
        e["notes"] = p["extraction_notes"]
    return e


def resolve_section(params: list, prof: dict) -> list:
    matched = [p for p in params if matches(p.get("applies_to", {}), prof)]
    # Among entries sharing a base name, keep only the most specific (resolves
    # generic-vs-mode-specific overlaps, e.g. 400G CD link budget 16QAM vs 8QAM).
    groups: dict = {}
    for p in matched:
        groups.setdefault(base_name(p["name"]), []).append(p)
    out = []
    for grp in groups.values():
        top = max(specificity(p.get("applies_to", {})) for p in grp)
        out.extend(to_entry(p) for p in grp if specificity(p.get("applies_to", {})) == top)
    out.sort(key=lambda e: e["source_id"])
    return out


def main():
    ds = json.loads(SRC.read_text(encoding="utf-8"))
    ident = {i["media_interface_id"]: i for i in ds["identity"]}
    opt = ds["optical_specs"]
    dwdm_normative = [p for p in opt["dwdm_link"] if p["category"] != "filter"]
    dwdm_filters = [p for p in opt["dwdm_link"] if p["category"] == "filter"]

    profiles = {g: [] for g in GROUP_ORDER}
    for mid, i in ident.items():
        sr_nom = nominal_rate(i["symbol_rate_GBd"])
        prof = {
            "profile_id": mid,
            "media_interface_id": mid,
            "format": i["format"],
            "line_rate_G": i["payload_rate_G"],
            "modulation": i["modulation"],
            "symbol_rate_GBd": i["symbol_rate_GBd"],
            "symbol_rate_G_nominal": sr_nom,
            "designation_type": designation(i["power_class"], sr_nom),
            "power_class": i["power_class"],
            "add_drop": i["add_drop_type"],
            "supported_grids_GHz": supported_grids(sr_nom),
            "sff8024_id_hex": i.get("sff8024_id_hex"),
            "tx_optical": resolve_section(opt["tx_optical"], _grid_ctx(i, sr_nom)),
            "rx_optical": resolve_section(opt["rx_optical"], _grid_ctx(i, sr_nom)),
            "dwdm_link": resolve_section(dwdm_normative, _grid_ctx(i, sr_nom)),
        }
        profiles[prof["designation_type"]].append(prof)

    for g in profiles:
        profiles[g].sort(key=lambda p: -p["line_rate_G"])

    out_doc = {
        "view": "mode_centric",
        "description": "Pivoted view of OpenZR+ optical_specs grouped by line rate/mode and "
                       "designation type. Derived from output/openzrplus_dataset.json; "
                       "per-parameter applies_to filters resolved to concrete per-mode values.",
        "derived_from": "output/openzrplus_dataset.json",
        "schema_note": "Convenience view — shape differs from openzrplus.schema.json and is not validated against it.",
        "meta": {k: ds["meta"][k] for k in ("standard_name", "version", "revision_date",
                                            "source_url", "dataset_version", "extraction_status")},
        "generated": str(date.today()),
        "designation_types": DESIGNATION_LEGEND,
        "shared": {
            "mux_demux_filter_example_75GHz": [to_entry(p) for p in dwdm_filters],
            "mask_profiles": opt["mask_profiles"],
        },
        "profiles_by_designation": {g: profiles[g] for g in GROUP_ORDER},
    }
    OUT.write_text(json.dumps(out_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(len(v) for v in profiles.values())
    print(f"Wrote {OUT}")
    print(f"designation groups: {[(g, len(profiles[g])) for g in GROUP_ORDER]}")
    print(f"total profiles: {total}")
    for g in ["60LA", "60HA", "80HA"]:
        if profiles[g]:
            p = profiles[g][0]
            print(f"  {g} sample [{p['profile_id']}]: tx={len(p['tx_optical'])} "
                  f"rx={len(p['rx_optical'])} dwdm={len(p['dwdm_link'])}")


def _grid_ctx(i: dict, sr_nom: int) -> dict:
    return {
        "format": i["format"],
        "modulation": i["modulation"],
        "power_class": i["power_class"],
        "add_drop": i["add_drop_type"],
        "symbol_rate_G_nominal": sr_nom,
        "supported_grids_GHz": supported_grids(sr_nom),
    }


if __name__ == "__main__":
    main()
