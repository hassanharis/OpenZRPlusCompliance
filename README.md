# OpenZR+ Compliance Dataset — Project README

> Cursor: Read this first. It is the authoritative map of this project.

---

## What this is

A pipeline that converts the OpenZR+ MSA Technical Specification Rev 3.0 PDF
into a structured, schema-validated JSON dataset, then uses that dataset for
deterministic compliance checking of optical transceiver datasheets.

**The goal**: pre-qualification, compliance verification, and performance
benchmarking of optical transceivers against OpenZR+ — extensible to cross-
examine against OIF-400ZR, ITU-T G.709, SFF-8024, IEEE 802.3, and CMIS.

---

## File map

```
openzrplus-schema/
├── README.md                          ← You are here
├── openzrplus.schema.json             ← JSON Schema (draft-07). Ground truth for data shape.
│
├── prompts/
│   ├── EXTRACTION_SYSTEM_PROMPT.md    ← System prompt for ALL API calls in the pipeline
│   └── EXTRACTION_PASSES.md          ← 9 user prompts, one per extraction pass
│
├── scripts/
│   ├── extract_pipeline.py            ← Main pipeline: PDF → JSON dataset (9 passes)
│   └── compliance_checker.py          ← Checker: vendor datasheet JSON → pass/fail report
│
└── output/                            ← Generated files (git-ignored until frozen)
    ├── openzrplus_dataset.json        ← Assembled dataset (set status to "frozen" after review)
    └── gap_report.json                ← LLM gap-check output
```

---

## Quickstart

```bash
# 1. Install deps
pip install anthropic pdfplumber jsonschema

# 2. Download the PDF
curl -o openzrplus_rev3p0_final2.pdf \
  https://openzrplus.org/wp-content/uploads/2024/04/openzrplus_rev3p0_final2.pdf

# 3. Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# 4. Run extraction (all 9 passes, with caching)
cd scripts
python extract_pipeline.py --pdf ../openzrplus_rev3p0_final2.pdf

# 5. Run a single pass (e.g. during development)
python extract_pipeline.py --pdf ../openzrplus_rev3p0_final2.pdf --passes tx_optical

# 6. Skip gap check for faster iteration
python extract_pipeline.py --pdf ../openzrplus_rev3p0_final2.pdf --skip-gap

# 7. Check a vendor datasheet
python compliance_checker.py \
  --dataset ../output/openzrplus_dataset.json \
  --vendor ../your_vendor_datasheet.json \
  --out ../output/vendor_report.json
```

---

## Extraction pipeline — how it works

```
PDF
 │
 ├─ pdfplumber: extract text + tables per page range
 │
 ├─ Pass 1–8: LLM extracts one section per call
 │   system = EXTRACTION_SYSTEM_PROMPT.md (same for all passes)
 │   user   = PDF text + section-specific prompt from EXTRACTION_PASSES.md
 │   output = partial JSON fragment for that section
 │
 ├─ Assembler: merges all pass outputs into one dataset
 │
 ├─ Pass 9 (gap check): LLM reviews full doc vs assembled dataset
 │   output = gap_report.json (missing params, wrong values, dropped footnotes)
 │
 ├─ JSON Schema validation (jsonschema library)
 │
 └─ Quality checks (business logic: min/max coverage, mask point counts, etc.)
```

**Caching**: Results per pass are cached in `.extraction_cache/`. Re-running
the pipeline skips passes whose PDF page range hasn't changed. Use `--no-cache`
to force re-extraction.

---

## The 9 extraction passes

| Pass | Section | Output key | Critical watch-outs |
|------|---------|------------|---------------------|
| 1 | Tables 1-2a/1-3/1-4a | `identity[]` | Merge 3 tables; HA/HB split |
| 2 | §1/§7/§8 | `line_encoding[]` | ±20ppm tolerance; ZR100 is 30G |
| 3 | §3/§5 | `framing[]` | 257-bit block counts; MSI byte location |
| 4 | §11.1 Table 11-1 | `dwdm_link[]` | 75G vs 100G grid rows |
| 5 | §11.2 Tables 11-2/11-2a | `tx_optical[]` | Most footnotes; HA/HB column split |
| 6 | §11.3 Table 11-3 | `rx_optical[]` | OSNR varies by format + grid |
| 7 | §11.2.1/11.2.2/11.4.10/11.4.11 | `mask_profiles[]` | Full breakpoint arrays required |
| 8 | All sections | `compliance_rules[]` | predicate_type routing |
| 9 | Full doc + dataset | `gap_report.json` | Verification — not assembly |

---

## Schema design decisions

### Why `applies_to` is a structured object, not a string

Your original schema used compound strings like `"80HB+400ZR+"`. These are
opaque and can't be queried. The structured filter:

```json
"applies_to": {
  "format": ["400ZR+"],
  "symbol_rate_G": [80],
  "power_class": ["HB"],
  "add_drop": ["colorless"]
}
```

lets the checker answer: "give me all limits that apply to my specific module"
without string parsing.

### Why mask profiles are separate from numeric params

Sections §11.2.1, §11.2.2, §11.4.10, §11.4.11 define frequency-domain masks —
piecewise linear breakpoint arrays. They cannot be expressed as a single
min/max scalar. They live in `optical_specs.mask_profiles[]` as point arrays.

### Why Tables 1-2a, 1-3, 1-4a are merged

They are three views of the same entity (media_interface_id). Keeping them
separate means any query about a specific MID has to join three arrays.
The merged `identity[]` array has one object per MID.

### severity field

Maps directly to RFC 2119 language in the standard:
- `mandatory`    → SHALL
- `conditional`  → SHALL WHEN [condition]
- `recommended`  → SHOULD
- `informative`  → MAY / for reference only

Only `mandatory` failures cause overall verdict `FAIL`.

### extraction_status lifecycle

```
draft → llm_extracted → human_verified → frozen
```

**Never use the dataset for production compliance checks until status = frozen.**
The compliance checker will warn if you try to check against a non-frozen dataset.

---

## Vendor datasheet format (input to compliance checker)

Normalise vendor datasheets to this shape before checking:

```json
{
  "vendor":              "Coherent",
  "part_number":         "QSFP-DD-400ZR-HA",
  "media_interface_id":  "ZR400-OFEC-16QAM-HA",
  "params": {
    "tx_output_power_dBm":        2.0,
    "tx_output_power_min_dBm":    0.0,
    "tx_output_power_max_dBm":    3.0,
    "rx_input_power_min_dBm":     -18.0,
    "rx_input_power_max_dBm":     -8.0,
    "channel_frequency_THz":      193.1,
    "osnr_tolerance_dB":          18.5,
    "tx_linewidth_MHz":           300,
    "chromatic_dispersion_ps_nm": 40000
  }
}
```

The normaliser (not included here — build per your datasheet sources) is
responsible for mapping vendor param names to the canonical names and aliases
in the dataset. Use `aliases[]` in each `numeric_param` to map vendor strings.

---

## Cross-standard examination

Every parameter has `cross_standard_refs[]`. To compare OpenZR+ against
another standard for a specific param:

```python
from scripts.compliance_checker import load_dataset

dataset = load_dataset("output/openzrplus_dataset.json")
tx = dataset["optical_specs"]["tx_optical"]

# Find all params with a cross-ref to OIF-400ZR
oif_params = [
    p for p in tx
    if any(r["standard_id"] == "OIF-400ZR-01.0"
           for r in p.get("cross_standard_refs", []))
]
```

When you add OIF-400ZR and G.709 datasets with the same schema, you can do
direct field-by-field comparison across standards for any given parameter.

---

## Adding a new standard

1. Copy this schema. Change `meta.standard_name` and `meta.version`.
2. Add new extraction passes in a new `EXTRACTION_PASSES_<standard>.md`.
3. Add cross-refs pointing back to OpenZR+ in the new dataset.
4. In the compliance checker, load both datasets and compare overlapping params.

The schema's `cross_standard_refs[].relationship` enum supports:
`equivalent`, `subset`, `superset`, `references`, `conflicts`, `informs`.
