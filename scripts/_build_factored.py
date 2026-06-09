#!/usr/bin/env python3
"""
Fold the expanded OpenZR+ optical specs into the axis-factored form.

Reads output/openzrplus_dataset.json (the expanded, schema-validated dataset),
folds the ~122 optical_specs parameter objects into ~N parameters of the shape

    "<key>": { name, category, unit?, check_type?, severity?, aliases?,
               depends_on:[axes],
               base:    { id, when, min/max, ... },          # the when=all variant
               overrides:[ { id, when, min/max, ... }, ... ] # sparse, by axis }

writes output/openzrplus.factored.json, validates it against
openzrplus.factored.schema.json, then proves equivalence by expanding the
factored form back to flat parameter objects and asserting an exact per-id match
with the source. Finally regenerates the routing index from the factored-expanded
dataset and diffs it against the existing one to prove downstream parity.

Run: python scripts/_build_factored.py
"""

import re
import sys
import json
import copy
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "openzrplus_dataset.json"
OUT = ROOT / "output" / "openzrplus.factored.json"
FSCHEMA = ROOT / "openzrplus.factored.schema.json"

AXIS_MAP = {
    "format": "payload_rate", "modulation": "modulation", "symbol_rate_G": "symbol_rate",
    "power_class": "power_profile", "add_drop": "power_profile", "grid_GHz": "grid",
}
DIMS = list(AXIS_MAP)
# Fields that are always carried per-variant (identity + the value differentiators).
PV_ALWAYS = {"id", "name", "category", "applies_to", "min", "max", "typical",
             "footnotes", "extraction_notes", "reference"}


def base_name(n: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", n).strip()


def slug(s: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", base_name(s).lower()).strip("_")
    return re.sub(r"_+", "_", s)


def specificity(applies_to: dict) -> int:
    a = applies_to or {}
    return sum(1 for k in DIMS if k in a and a[k] != ["ALL"])


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def fold_param(entries: list, param_name: str) -> dict:
    """Build one factored parameter object from a list of source entries."""
    all_keys = set()
    for e in entries:
        all_keys |= set(e.keys())
    hoist_keys = sorted(all_keys - PV_ALWAYS)

    hoisted = {}
    for f in hoist_keys:
        present = [f in e for e in entries]
        vals = {canon(e[f]) for e in entries if f in e}
        if all(present) and len(vals) == 1:
            hoisted[f] = entries[0][f]

    base = None
    overrides = []
    for e in entries:
        v = {"id": e["id"], "when": e.get("applies_to", {})}
        if e["name"] != param_name:
            v["label"] = e["name"]
        for f in sorted(all_keys):
            if f in ("id", "name", "category", "applies_to"):
                continue
            if f in hoisted:
                continue
            if f in e:
                v[f] = e[f]
        if specificity(e.get("applies_to", {})) == 0:
            base = v
        else:
            overrides.append(v)

    distinct_vals = {(e.get("min"), e.get("max")) for e in entries}
    axes = set()
    if len(distinct_vals) > 1:
        for e in entries:
            a = e.get("applies_to", {})
            for k in DIMS:
                if k in a and a[k] != ["ALL"]:
                    axes.add(AXIS_MAP[k])

    param = {"name": param_name, "category": entries[0]["category"]}
    for f in ("unit", "check_type", "severity", "aliases", "unit_aliases",
              "unit_scale_to_si", "test_conditions", "cross_standard_refs",
              "extraction_confidence"):
        if f in hoisted:
            param[f] = hoisted[f]
    # any other hoisted fields (rare)
    for f in hoisted:
        if f not in param:
            param[f] = hoisted[f]
    param["depends_on"] = sorted(axes)
    if base is not None:
        param["base"] = base
    if overrides:
        param["overrides"] = overrides
    return param


def build_factored(ds: dict) -> dict:
    opt = ds["optical_specs"]
    src = opt["dwdm_link"] + opt["tx_optical"] + opt["rx_optical"]

    groups = {}
    order = []
    for p in src:
        key = (p["category"], base_name(p["name"]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    params = {}

    def put(key, obj):
        k = key
        i = 2
        while k in params:
            k = f"{key}_{i}"
            i += 1
        params[k] = obj

    for key in order:
        cat, bn = key
        entries = groups[key]
        sigs = [canon(e.get("applies_to", {})) for e in entries]
        if len(set(sigs)) == len(sigs):
            put(slug(bn), fold_param(entries, bn))
        else:
            # Duplicate axis-signatures => not pure axis variants (condition
            # variants like RIN avg/peak, jitter bands, PDL penalty levels).
            for e in entries:
                put(slug(e["name"]), fold_param([e], e["name"]))

    return {
        "$schema": "../openzrplus.factored.schema.json",
        "view": "factored",
        "description": "Axis-factored source-of-truth for OpenZR+ optical specs "
                       "(base + sparse overrides). The expanded dataset, mode view, "
                       "and routing index are projections of this.",
        "derived_from": "output/openzrplus_dataset.json",
        "meta": ds["meta"],
        "axes": {
            "payload_rate":  ["400ZR+", "300ZR+", "200ZR+", "100ZR+"],
            "modulation":    ["DP-16QAM", "DP-8QAM", "DP-QPSK"],
            "symbol_rate_G": [30, 60, 80],
            "power_profile": ["baseline", "HA", "HB"],
            "add_drop":      ["colored", "colorless"],
            "grid_GHz":      [75, 100],
        },
        "identity": ds["identity"],
        "optical_parameters": params,
        "mask_profiles": {m["mask_id"]: m for m in opt["mask_profiles"]},
        "semantic_rules": [r for r in ds["compliance_rules"]
                           if not r["rule_id"].startswith("R-")],
    }


def expand(factored: dict) -> list:
    """Reconstruct the flat list of optical parameter objects from factored form."""
    out = []
    for key, p in factored["optical_parameters"].items():
        hoisted = {f: v for f, v in p.items()
                   if f not in ("name", "category", "depends_on", "base", "overrides")}
        variants = ([p["base"]] if "base" in p else []) + p.get("overrides", [])
        for v in variants:
            obj = {"id": v["id"], "name": v.get("label", p["name"]),
                   "category": p["category"], "applies_to": v["when"]}
            for f, val in hoisted.items():
                obj[f] = val
            for f, val in v.items():
                if f in ("id", "when", "label"):
                    continue
                obj[f] = val
            out.append(obj)
    return out


def roundtrip_check(ds: dict, factored: dict) -> int:
    src = ds["optical_specs"]["dwdm_link"] + ds["optical_specs"]["tx_optical"] + ds["optical_specs"]["rx_optical"]
    exp = expand(factored)
    src_by_id = {p["id"]: p for p in src}
    exp_by_id = {p["id"]: p for p in exp}
    errs = []
    if set(src_by_id) != set(exp_by_id):
        errs.append(f"id set mismatch: missing={set(src_by_id) - set(exp_by_id)} extra={set(exp_by_id) - set(src_by_id)}")
    for pid in sorted(set(src_by_id) & set(exp_by_id)):
        if canon(src_by_id[pid]) != canon(exp_by_id[pid]):
            errs.append(f"mismatch {pid}:\n   src={canon(src_by_id[pid])}\n   exp={canon(exp_by_id[pid])}")
    if errs:
        print("ROUND-TRIP FAILED:")
        for e in errs[:20]:
            print("  " + e)
        raise SystemExit(1)
    return len(src)


def regenerate_routing_index(ds: dict, factored: dict):
    """Rebuild a dataset purely from the factored form and regenerate the routing
    index from it, then diff against the existing one (ignoring the date)."""
    exp = expand(factored)
    by_cat = {"dwdm_link": [], "tx_optical": [], "rx_optical": []}
    for p in exp:
        cat = "dwdm_link" if p["category"] in ("dwdm_link", "filter") else p["category"]
        by_cat[cat].append(p)
    recon = copy.deepcopy(ds)
    recon["optical_specs"]["dwdm_link"] = by_cat["dwdm_link"]
    recon["optical_specs"]["tx_optical"] = by_cat["tx_optical"]
    recon["optical_specs"]["rx_optical"] = by_cat["rx_optical"]
    recon["compliance_rules"] = factored["semantic_rules"]

    tmp_ds = ROOT / "output" / "_recon_dataset.json"
    tmp_idx = ROOT / "output" / "_recon_routing_index.json"
    tmp_ds.write_text(json.dumps(recon, ensure_ascii=False), encoding="utf-8")

    sys.path.insert(0, str(ROOT / "scripts"))
    import _build_routing_index as bri
    bri.SRC, bri.OUT = tmp_ds, tmp_idx
    bri.main()

    existing = ROOT / "output" / "openzrplus_routing_index.json"
    a = json.loads(tmp_idx.read_text(encoding="utf-8"))
    b = json.loads(existing.read_text(encoding="utf-8"))
    for d in (a, b):
        d.pop("generated", None)
    same = canon(a["index"]) == canon(b["index"])
    tmp_ds.unlink(missing_ok=True)
    tmp_idx.unlink(missing_ok=True)
    return same


def main():
    ds = json.loads(SRC.read_text(encoding="utf-8"))
    factored = build_factored(ds)
    OUT.write_text(json.dumps(factored, indent=2, ensure_ascii=False), encoding="utf-8")

    schema = json.loads(FSCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(factored)

    n_src = roundtrip_check(ds, factored)
    n_params = len(factored["optical_parameters"])
    n_rules_before = len(ds["compliance_rules"])
    n_rules_after = len(factored["semantic_rules"])
    folded = sum(1 for p in factored["optical_parameters"].values() if p.get("overrides"))
    invariant = sum(1 for p in factored["optical_parameters"].values() if not p.get("depends_on"))

    parity = regenerate_routing_index(ds, factored)

    print(f"Wrote {OUT}")
    print(f"Factored schema validation: PASSED")
    print(f"Round-trip equivalence: PASSED ({n_src} source params reproduced exactly)")
    print(f"  optical parameter objects: {n_src} -> {n_params} factored keys "
          f"({100 * (1 - n_params / n_src):.0f}% fewer)")
    print(f"  parameters with overrides (multi-mode): {folded}")
    print(f"  invariant parameters (depends_on=[]): {invariant}")
    print(f"  compliance rules: {n_rules_before} -> {n_rules_after} semantic "
          f"(per-parameter rules folded into the parameters)")
    print(f"Routing index regenerated from factored form matches existing: {parity}")


if __name__ == "__main__":
    main()
