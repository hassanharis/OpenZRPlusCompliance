# Per-Section Extraction Prompts

These are the `user` messages for each extraction pass. Each pass targets one
logical section of the OpenZR+ PDF. Run them in order. The output of each pass
feeds into the assembler script.

---

## Pass 1 — Identity table (Tables 1-2a, 1-3, 1-4a)

**Goal**: Populate `identity[]`. Merge all three tables into one array keyed
by `media_interface_id`.

```
Extract every media interface ID defined in Tables 1-2a, 1-3, and 1-4a of the
provided text.

For each distinct media_interface_id, output one JSON object matching the
`identity` array item schema. Merge information from all three tables into each
object — do NOT output three separate objects for the same media_interface_id.

Pay special attention to:
- TBD SFF-8024 IDs: set sff8024_id_decimal and sff8024_id_hex to null
- The HA/HB power class distinction: HA = 0dBm colored, HB = 0dBm colorless
- Min Tx power values: baseline 400ZR+ = -10dBm, HA = 0dBm, 200ZR+ baseline = -9dBm, 100ZR+ baseline = -8dBm
- supported_host_interfaces: derive from Table 1-1 and Table 1-5
- application_bit_rate_Gbs is the wire rate (e.g. 481.108374 Gb/s for 400ZR+)

Output format: { "identity": [ ...objects... ] }
```

---

## Pass 2 — Line encoding (Table 1-3, §7, §8)

**Goal**: Populate `line_encoding[]`.

```
Extract line encoding parameters for each media_interface_id from Table 1-3
and the OFEC/symbol-mapping sections (§7, §8).

For each media_interface_id, output one JSON object matching the `line_encoding`
array item schema.

Pay special attention to:
- symbol_rate_tolerance_ppm = 20 for all modes (stated as ±20ppm in Table 1-3)
- The 100ZR+ baud rate is 30.069273399 GBd, not 60 GBd
- OFEC NCG = 11.6 dB for all modes
- pre_fec_ber = 2.0e-2 for all modes
- encoding = "absolute" (non-differential) for all modes
- Reference §7.1 for the OFEC codec definition

Output format: { "line_encoding": [ ...objects... ] }
```

---

## Pass 3 — Framing structures (§3, §5, Tables 3-1 through 3-2)

**Goal**: Populate `framing[]`. One entry per ZR frame format.

```
Extract ZR frame structure parameters from §3 and §5, using Table 3-1 as the
primary numeric source.

For each frame format (ZR100, ZR200, ZR300, ZR400), output one JSON object
matching the `framing` array item schema.

Pay special attention to:
- block_size_bits = 257 for all formats (constant)
- oh_257b_blocks from Table 3-1 (column "First row 257-bit blocks allocated to AM/PAD/OH")
- payload_257b_blocks_per_4frames from Table 3-1
- am_lanes: ZR100=4, ZR200=8, ZR300=12, ZR400=16 (derived from §3.2–3.5)
- oh_blocks_count: ZR100=1, ZR200=2, ZR300=3, ZR400=4 (each block = 320 bits)
- pad_bits: ZR100=5, ZR200=10, ZR300=15, ZR400=20
- multiframe_depth = 16 for ZR400 (from §3.2); check §3.3–3.5 for others
- msi_byte_location = "row 4, byte 5" (from §3.7, only defined for ZR400)
- Add cross_standard_refs to OIF-400ZR-01.0 (ZR400 frame is based on it) and G.709 (MFAS field)

Output format: { "framing": [ ...objects... ] }
```

---

## Pass 4 — DWDM link specs (§11.1, Table 11-1)

**Goal**: Populate `optical_specs.dwdm_link[]`.

```
Extract all DWDM link parameters from Table 11-1 in §11.1.

For each row in the table, output one JSON object matching the `numeric_param`
schema. Use category = "dwdm_link" for all entries.

Pay special attention to:
- Extract BOTH the 75 GHz grid and 100 GHz grid spacing rows as separate params
  with applies_to.grid_GHz set appropriately
- Channel frequency range: applies to ALL formats and power classes
- Dispersion compensation range: note the units carefully (ps/nm)
- PDL: note whether this is a link budget item vs. a per-component spec
- Any parameters that differ between Appendix 13 (75 GHz examples) and
  Appendix 14 (100 GHz examples) vs. the normative Table 11-1 — flag this
  in extraction_notes

Output format: { "dwdm_link": [ ...objects... ] }
```

---

## Pass 5 — Tx optical specs (§11.2, Tables 11-2 and 11-2a)

**Goal**: Populate `optical_specs.tx_optical[]`.

```
Extract all Tx optical parameters from Tables 11-2 and 11-2a in §11.2.

For each parameter row, output one JSON object matching the `numeric_param`
schema. Use category = "tx_optical" for all entries.

This is the most complex table in the spec. Critical rules:
- Each row may apply to a SUBSET of media_interface_ids. Decompose applies_to
  carefully using the structured filter. Never use compound strings.
- The HA/HB column split means some rows have DIFFERENT limits for different
  power classes — output these as SEPARATE objects with different applies_to.
- Footnotes in this table are CRITICAL and frequently modify limits.
  Capture ALL footnotes for each row in footnotes[] and reflect the condition
  in test_conditions{}.
- Tx output power: baseline=-10dBm min, HA/HB=0dBm min (different rows)
- Frequency error tolerance: check if it differs between 60G and 80G modes
- Linewidth/laser phase noise: reference §11.2.1 for the mask — do NOT
  extract as a scalar; set check_type="mask" and reference the mask_id
- Add cross_standard_refs to OIF-400ZR Table 6-2 for shared parameters

Output format: { "tx_optical": [ ...objects... ] }
```

---

## Pass 6 — Rx optical specs (§11.3, Table 11-3)

**Goal**: Populate `optical_specs.rx_optical[]`.

```
Extract all Rx optical parameters from Table 11-3 in §11.3.

For each parameter row, output one JSON object matching the `numeric_param`
schema. Use category = "rx_optical" for all entries.

Pay special attention to:
- OSNR tolerance: this is the most critical Rx parameter. It varies by:
  - format (400ZR+ vs 300ZR+ etc.)
  - symbol rate (60G vs 80G)
  - grid spacing (75 GHz vs 100 GHz)
  Each combination should be a separate object.
- Maximum input power: check for differences between HA/HB and baseline
- Rx DGD tolerance: §11.4.3 has the definition — cross-reference it
- PDL tolerance: §11.4.6 has the definition
- Polarization rotation speed: §11.4.7 — note the unit is krad/s
- OOB OSNR definition: §11.4.2 — reference it in the cross_standard_refs
  (G.709 has an analogous concept)
- Any parameter measured "at the Rx" (RS) vs "at the Source" (SS) — capture
  in test_conditions.launch_condition

Output format: { "rx_optical": [ ...objects... ] }
```

---

## Pass 7 — Mask profiles (§11.2.1, §11.2.2, §11.4.10, §11.4.11)

**Goal**: Populate `optical_specs.mask_profiles[]`.

```
Extract all frequency-domain mask profiles from §11.2.1 (laser frequency noise),
§11.2.2 (Tx clock phase noise), §11.4.10 (Tx spectral mask 60G), and §11.4.11
(Tx spectral mask 80G).

For each mask figure/table, output one JSON object matching the `mask_profile`
schema.

CRITICAL: These are NOT scalar min/max parameters. Output the complete
breakpoint array as points[]. Each point is { freq_offset_GHz, limit_dBc }.
Read every breakpoint from the figure axes — do not summarise.

Pay special attention to:
- §11.4.10 applies_to symbol_rate_G=[60], §11.4.11 applies_to symbol_rate_G=[80]
- The x-axis units may differ between masks (GHz vs MHz for phase noise)
  — normalise to GHz in the output, set x_axis_unit accordingly
- The y-axis may be dBc/Hz for phase noise vs dBc for spectral masks
  — set y_axis_unit accurately
- If a figure shows a multi-segment piecewise mask, capture ALL segments
  as breakpoints (minimum: every corner/inflection point)
- mask_type values: "tx_spectral", "laser_freq_noise", "tx_clock_phase_noise"

Output format: { "mask_profiles": [ ...objects... ] }
```

---

## Pass 8 — Compliance rules (all sections)

**Goal**: Populate `compliance_rules[]`.

```
Derive structured compliance rules from the complete specification text.

For EACH of the following, output one JSON object matching the `compliance_rule`
schema:

MANDATORY rules to extract:
1. SFF-8024 Media Interface ID match (Table 1-3/1-4a) → predicate_type="enum_match"
2. Baud rate within ±20ppm tolerance → predicate_type="numeric_tolerance"
3. Modulation format match per media_interface_id → predicate_type="enum_match"
4. OFEC NCG ≥ 11.6 dB → predicate_type="numeric_range"
5. Pre-FEC BER threshold (2.0e-2) → predicate_type="numeric_range"
6. All tx_optical params within their min/max → predicate_type="numeric_range"
7. All rx_optical params within their min/max → predicate_type="numeric_range"
8. All dwdm_link params within their min/max → predicate_type="numeric_range"
9. Tx spectral mask compliance → predicate_type="mask"
10. Frame structure: 257-bit block alignment → predicate_type="numeric_range"
11. MSI byte value per multiplexing mode (Table 3-2) → predicate_type="table_lookup"
12. Only same-rate clients may be multiplexed (no mixed modes) → predicate_type="prose_rag"
13. GMP across 4-frame group constraint → predicate_type="cross_param_ratio"
14. OFEC codec polynomial compliance (§7.4) → predicate_type="prose_rag"

For prose_rag rules: set rag_fallback=true and write a clear statement that
a RAG query over the standard PDF can verify.

For each rule, set parameter_ref to the relevant numeric_param id where one exists.

Output format: { "compliance_rules": [ ...objects... ] }
```

---

## Pass 9 — Verification / gap check

**Goal**: Find what was missed, not what was found.

```
You are reviewing a completed extraction of the OpenZR+ MSA Rev 3.0.

Given:
1. The complete standard text (provided below)
2. The extracted JSON dataset (provided below)

Your task is to identify GAPS and ERRORS — things that are in the standard
but missing or wrong in the JSON. Output a JSON object with this structure:

{
  "missing_params": [
    { "section": "§11.2", "table": "Table 11-2a", "param": "...", "reason": "..." }
  ],
  "wrong_values": [
    { "param_id": "...", "extracted_value": ..., "correct_value": ..., "evidence": "..." }
  ],
  "dropped_conditions": [
    { "param_id": "...", "missing_condition": "...", "evidence": "..." }
  ],
  "dropped_footnotes": [
    { "param_id": "...", "footnote_text": "...", "impact": "..." }
  ],
  "cross_ref_gaps": [
    { "param_id": "...", "missing_ref": "...", "reason": "..." }
  ]
}

Be thorough. A missed condition is worse than a missing parameter.
```
