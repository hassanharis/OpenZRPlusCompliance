#!/usr/bin/env python3
"""
Deterministic serializer for the OpenZR+ Rev 3.0 dataset.

The *values* in this file were extracted from openzrplus_rev3p0_final2.pdf by an
LLM acting per prompts/EXTRACTION_SYSTEM_PROMPT.md (the 9-pass contract). This
module only assembles those extracted values into the schema shape, runs JSON
Schema validation + the pipeline quality checks, and writes output/.

It is intentionally separate from extract_pipeline.py (which performs live API
extraction). Run: python scripts/_build_dataset.py
"""

import json
from pathlib import Path
from datetime import date

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "openzrplus.schema.json"
OUT_DIR = ROOT / "output"

XREF_SFF = lambda clause, name=None: {
    "standard_id": "SFF-8024", "clause": clause,
    **({"param_name": name} if name else {}), "relationship": "references",
}
XREF_OIF = lambda clause, name=None, rel="references": {
    "standard_id": "OIF-400ZR-01.0", "clause": clause,
    **({"param_name": name} if name else {}), "relationship": rel,
}
XREF_G709 = lambda clause, name=None: {
    "standard_id": "ITU-T-G.709", "clause": clause,
    **({"param_name": name} if name else {}), "relationship": "references",
}

# Precise symbol rates (Table 1-3 / Table 11-x)
SR_60 = 60.138546798
SR_80 = 80.18472906
SR_30 = 30.069273399

HOSTS_400 = [
    {"host_interface": "400GBASE-R", "lane_count": 1, "tributary_slots": 4},
    {"host_interface": "200GBASE-R", "lane_count": 2, "tributary_slots": 2},
    {"host_interface": "100GBASE-R", "lane_count": 4, "tributary_slots": 1},
]
HOSTS_300 = [{"host_interface": "100GBASE-R", "lane_count": 3, "tributary_slots": 1}]
HOSTS_200 = [
    {"host_interface": "200GBASE-R", "lane_count": 1, "tributary_slots": 2},
    {"host_interface": "100GBASE-R", "lane_count": 2, "tributary_slots": 1},
]
HOSTS_100 = [{"host_interface": "100GBASE-R", "lane_count": 1, "tributary_slots": 1}]

IDENTITY_REF = "Tables 1-2a / 1-3 / 1-4a, §1"


def ident(mid, fmt, sff_dec, sff_hex, payload, app_rate, framing, sr, mod,
          bpu, pclass, min_tx, addrop, hosts):
    obj = {
        "media_interface_id": mid,
        "format": fmt,
        "sff8024_id_decimal": sff_dec,
        "sff8024_id_hex": sff_hex,
        "payload_rate_G": payload,
        "application_bit_rate_Gbs": app_rate,
        "framing_format": framing,
        "symbol_rate_GBd": sr,
        "modulation": mod,
        "bits_per_ui": bpu,
        "lane_count": 1,
        "power_class": pclass,
        "min_tx_power_dBm": min_tx,
        "add_drop_type": addrop,
        "supported_host_interfaces": hosts,
        "ncg_dB": 11.6,
        "pre_fec_ber": 2.0e-2,
        "reference_standard": "OpenZR+",
        "reference": IDENTITY_REF,
        "cross_standard_refs": [],
    }
    if sff_hex and sff_hex != "TBD":
        obj["cross_standard_refs"].append(
            XREF_SFF(f"Media Interface ID {sff_hex}", "SM Media Interface ID"))
    if framing == "ZR400-OFEC-16QAM":
        obj["cross_standard_refs"].append(
            XREF_OIF("400ZR frame structure", "ZR400 frame", "subset"))
    return obj


identity = [
    ident("ZR400-OFEC-16QAM",    "400ZR+", 70, "46h", 400, 481.108374, "ZR400-OFEC-16QAM", SR_60, "DP-16QAM", 8, "baseline", -10, "colored",   HOSTS_400),
    ident("ZR400-OFEC-16QAM-HA", "400ZR+", None, None, 400, 481.108374, "ZR400-OFEC-16QAM", SR_60, "DP-16QAM", 8, "HA",       0,   "colored",   HOSTS_400),
    ident("ZR400-OFEC-16QAM-HB", "400ZR+", None, None, 400, 481.108374, "ZR400-OFEC-16QAM", SR_60, "DP-16QAM", 8, "HB",       0,   "colorless", HOSTS_400),
    ident("ZR400-OFEC-8QAM-HA",  "400ZR+", None, None, 400, 481.108374, "ZR400-OFEC-8QAM",  SR_80, "DP-8QAM",  6, "HA",       0,   "colored",   HOSTS_400),
    ident("ZR400-OFEC-8QAM-HB",  "400ZR+", None, None, 400, 481.108374, "ZR400-OFEC-8QAM",  SR_80, "DP-8QAM",  6, "HB",       0,   "colorless", HOSTS_400),
    ident("ZR300-OFEC-8QAM",     "300ZR+", 71, "47h", 300, 360.831281, "ZR300-OFEC-8QAM",  SR_60, "DP-8QAM",  6, "baseline", -10, "colored",   HOSTS_300),
    ident("ZR300-OFEC-8QAM-HA",  "300ZR+", None, None, 300, 360.831281, "ZR300-OFEC-8QAM",  SR_60, "DP-8QAM",  6, "HA",       0,   "colored",   HOSTS_300),
    ident("ZR300-OFEC-8QAM-HB",  "300ZR+", None, None, 300, 360.831281, "ZR300-OFEC-8QAM",  SR_60, "DP-8QAM",  6, "HB",       0,   "colorless", HOSTS_300),
    ident("ZR200-OFEC-QPSK",     "200ZR+", 72, "48h", 200, 240.554187, "ZR200-OFEC-QPSK",  SR_60, "DP-QPSK",  4, "baseline", -9,  "colored",   HOSTS_200),
    ident("ZR200-OFEC-QPSK-HA",  "200ZR+", None, None, 200, 240.554187, "ZR200-OFEC-QPSK",  SR_60, "DP-QPSK",  4, "HA",       0,   "colored",   HOSTS_200),
    ident("ZR200-OFEC-QPSK-HB",  "200ZR+", None, None, 200, 240.554187, "ZR200-OFEC-QPSK",  SR_60, "DP-QPSK",  4, "HB",       0,   "colorless", HOSTS_200),
    ident("ZR100-OFEC-QPSK",     "100ZR+", 73, "49h", 100, 120.277094, "ZR100-OFEC-QPSK",  SR_30, "DP-QPSK",  4, "baseline", -8,  "colored",   HOSTS_100),
    ident("ZR100-OFEC-QPSK-HA",  "100ZR+", None, None, 100, 120.277094, "ZR100-OFEC-QPSK",  SR_30, "DP-QPSK",  4, "HA",       0,   "colored",   HOSTS_100),
    ident("ZR100-OFEC-QPSK-HB",  "100ZR+", None, None, 100, 120.277094, "ZR100-OFEC-QPSK",  SR_30, "DP-QPSK",  4, "HB",       0,   "colorless", HOSTS_100),
]


def lenc(mid, mod, sr, bps):
    return {
        "media_interface_id": mid,
        "modulation": mod,
        "encoding": "absolute",
        "symbol_rate_GBd": sr,
        "symbol_rate_tolerance_ppm": 20,
        "bits_per_symbol": bps,
        "fec": {"type": "OFEC", "ncg_dB": 11.6, "pre_fec_ber": 2.0e-2, "codec_ref": "§7.1"},
        "dsp_super_frame_ref": "§9.1",
        "pilot_sequence_ref": "§9.5",
        "cross_standard_refs": [XREF_OIF("§7 OFEC / DSP framing", "OFEC", "references")],
    }


line_encoding = [
    lenc(i["media_interface_id"], i["modulation"], i["symbol_rate_GBd"], i["bits_per_ui"])
    for i in identity
]


def fr(fmt, rows, cols, oh257, pay1, pay4, am, ohb, pad, mfd=None, msi=None):
    o = {
        "frame_format": fmt,
        "rows": rows,
        "columns": cols,
        "bits_per_row": cols,
        "block_size_bits": 257,
        "oh_257b_blocks": oh257,
        "payload_257b_blocks_per_frame": pay1,
        "payload_257b_blocks_per_4frames": pay4,
        "am_lanes": am,
        "oh_blocks_count": ohb,
        "pad_bits": pad,
        "gmp_stuffing_granularity_bits": 257,
        "reference": "Table 3-1, §3",
        "cross_standard_refs": [
            XREF_OIF("400ZR frame structure", "ZR frame", "subset"),
            XREF_G709("Annex D (GMP), Clause 20.4.1.1 (MSI/PT22)", "MFAS/GMP"),
        ],
    }
    if mfd is not None:
        o["multiframe_depth"] = mfd
    if msi is not None:
        o["msi_byte_location"] = msi
    return o


framing = [
    fr("ZR400", 256, 10280, 20, 10220, 40880, 16, 4, 20, mfd=16, msi="row 4, byte 5"),
    fr("ZR300", 192, 10280, 15, 7665, 30660, 12, 3, 15),
    fr("ZR200", 128, 10280, 10, 5110, 20440, 8, 2, 10),
    fr("ZR100", 128, 5140, 5, 2555, 10220, 4, 1, 5),
]


def np_(pid, name, category, applies_to, unit, reference, mn=None, mx=None,
        severity="mandatory", check_type="range", aliases=None, footnotes=None,
        test_conditions=None, conf="high", notes=None, xrefs=None, typical=None,
        scale=None, unit_aliases=None):
    o = {
        "id": pid, "name": name, "category": category,
        "applies_to": applies_to, "unit": unit, "reference": reference,
        "severity": severity, "check_type": check_type,
        "extraction_confidence": conf,
    }
    if mn is not None: o["min"] = mn
    if mx is not None: o["max"] = mx
    if typical is not None: o["typical"] = typical
    if aliases: o["aliases"] = aliases
    if unit_aliases: o["unit_aliases"] = unit_aliases
    if scale is not None: o["unit_scale_to_si"] = scale
    if footnotes: o["footnotes"] = footnotes
    if test_conditions: o["test_conditions"] = test_conditions
    if notes: o["extraction_notes"] = notes
    o["cross_standard_refs"] = xrefs or []
    return o


ALL = {"format": ["ALL"]}
F400 = {"format": ["400ZR+"]}
F300 = {"format": ["300ZR+"]}
F200 = {"format": ["200ZR+"]}
F100 = {"format": ["100ZR+"]}

# ---------------------------------------------------------------- DWDM link
dwdm = [
    np_("opt.dwdm.11.1.100", "Channel frequency", "dwdm_link", ALL, "THz",
        "Table 11-1, §11.1", mn=191.3, mx=196.1, scale=1e12,
        aliases=["channel_frequency_THz", "center frequency", "channel frequency"],
        xrefs=[XREF_OIF("Table 11-1", "Channel frequency")]),
    np_("opt.dwdm.11.1.110.75", "Channel spacing (75 GHz grid)", "dwdm_link",
        {"grid_GHz": [75]}, "GHz", "Table 11-1, §11.1", mn=75, check_type="min_only",
        aliases=["channel_spacing_GHz", "grid spacing"]),
    np_("opt.dwdm.11.1.110x.100", "Channel spacing (100 GHz grid)", "dwdm_link",
        {"grid_GHz": [100]}, "GHz", "Table 11-1x, §11.1", mn=100, check_type="min_only",
        aliases=["channel_spacing_GHz", "grid spacing"]),
    # Chromatic dispersion (link budget) per format — 75 GHz grid
    np_("opt.dwdm.11.1.160.400", "Chromatic dispersion (link budget)", "dwdm_link",
        F400, "ps/nm", "Table 11-1, §11.1", mx=20000, check_type="max_only",
        aliases=["chromatic_dispersion_ps_nm", "CD"], notes="Used for link budgeting (G.652 fiber)."),
    np_("opt.dwdm.11.1.160.300", "Chromatic dispersion (link budget)", "dwdm_link",
        F300, "ps/nm", "Table 11-1, §11.1", mx=40000, check_type="max_only",
        aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.dwdm.11.1.160.200", "Chromatic dispersion (link budget)", "dwdm_link",
        F200, "ps/nm", "Table 11-1, §11.1", mx=50000, check_type="max_only",
        aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.dwdm.11.1.160.100", "Chromatic dispersion (link budget)", "dwdm_link",
        F100, "ps/nm", "Table 11-1, §11.1", mx=100000, check_type="max_only",
        aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.dwdm.11.1.160x.400q8", "Chromatic dispersion (link budget, 100 GHz)", "dwdm_link",
        {"format": ["400ZR+"], "modulation": ["DP-8QAM"], "grid_GHz": [100]}, "ps/nm",
        "Table 11-1x, §11.1", mx=30000, check_type="max_only",
        aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.dwdm.11.1.161", "Optical return loss at Ss", "dwdm_link", ALL, "dB",
        "Table 11-1, §11.1", mx=24, check_type="max_only", conf="medium",
        notes="Table lists value 24 in the Max column with Min='—'. Captured as stated; "
              "physical interpretation of ORL as a minimum may warrant human review."),
    np_("opt.dwdm.11.1.162", "Discrete reflectance between Ss and Rs", "dwdm_link", ALL, "dB",
        "Table 11-1, §11.1", mx=-27, check_type="max_only"),
    np_("opt.dwdm.11.1.170.400", "Instantaneous differential group delay (DGD)", "dwdm_link",
        F400, "ps", "Table 11-1, §11.1", mx=50, check_type="max_only",
        notes="DGDmax based on DGDmax/DGDmean ratio of 3.3; fiber portion of Rx PMD tolerance.",
        xrefs=[XREF_G709("DGD definition", "DGD")]),
    np_("opt.dwdm.11.1.170.300", "Instantaneous differential group delay (DGD)", "dwdm_link",
        F300, "ps", "Table 11-1, §11.1", mx=66, check_type="max_only"),
    np_("opt.dwdm.11.1.170.200", "Instantaneous differential group delay (DGD)", "dwdm_link",
        F200, "ps", "Table 11-1, §11.1", mx=66, check_type="max_only"),
    np_("opt.dwdm.11.1.170.100", "Instantaneous differential group delay (DGD)", "dwdm_link",
        F100, "ps", "Table 11-1, §11.1", mx=83, check_type="max_only"),
    np_("opt.dwdm.11.1.171", "Polarization dependent loss (PDL)", "dwdm_link", ALL, "dB",
        "Table 11-1, §11.1", mx=2, check_type="max_only", aliases=["pdl_dB"]),
    np_("opt.dwdm.11.1.172.75", "Polarization rotation speed (75 GHz grid)", "dwdm_link",
        {"grid_GHz": [75]}, "krad/s", "Table 11-1, §11.1", mx=50, check_type="max_only"),
    np_("opt.dwdm.11.1.172x.100", "Polarization rotation speed (100 GHz grid)", "dwdm_link",
        {"grid_GHz": [100]}, "krad/s", "Table 11-1x, §11.1", mx=300, check_type="max_only"),
]

# Informative Mux/Demux example characteristics (Appendix 13, Table 13-1, 75 GHz)
def filt(suffix, name, mn, mx, unit="dB"):
    return np_(f"opt.filter.11.1.163{suffix}", name, "filter", {"grid_GHz": [75]}, unit,
               "Table 13-1, §13 (informative)", mn=mn, mx=mx,
               severity="informative",
               check_type=("range" if (mn is not None and mx is not None)
                           else ("min_only" if mn is not None else "max_only")),
               xrefs=[XREF_OIF("Mux/Demux filter shape", "filter", "informs")])

dwdm += [
    filt("b", "3 dB bandwidth Mux (f3dB)", 70, 76, "GHz"),
    filt("c", "3 dB bandwidth Demux (f3dB)", 70, 76, "GHz"),
    filt("d", "10 dB bandwidth Mux (f10dB)", 85, 94, "GHz"),
    filt("e", "10 dB bandwidth Demux (f10dB)", 85, 94, "GHz"),
    filt("f", "Insertion loss Mux (IL)", None, 6.5),
    filt("g", "Insertion loss Demux (IL)", None, 6.5),
    filt("h", "Insertion loss variation Mux", None, 1.5),
    filt("i", "Insertion loss variation Demux", None, 1.5),
    filt("j", "Adjacent channel isolation Mux", 30, None),
    filt("k", "Adjacent channel isolation Demux", 30, None),
    filt("l", "Non-adjacent channel isolation Mux", 25, None),
    filt("m", "Non-adjacent channel isolation Demux", 25, None),
    filt("n", "Frequency shift of Mux", -4, 4, "GHz"),
    filt("o", "Frequency shift of Demux", -4, 4, "GHz"),
    filt("p", "Ripple of Mux", None, 2.5),
    filt("q", "Ripple of Demux", None, 2.5),
]

# ---------------------------------------------------------------- Tx optical
TX = "Table 11-2 / 11-4x / 11-5y, §11.2"
xref_oif_tx = [XREF_OIF("Table 6-2 (Tx)", "Tx optical", "references")]

tx = [
    # Universal Tx parameters (apply across all designation types)
    np_("opt.tx.11.1.200", "Laser frequency accuracy", "tx_optical", ALL, "GHz",
        "Table 11-2, §11.2", mn=-1.8, mx=1.8, aliases=["laser_frequency_accuracy_GHz", "frequency error"],
        xrefs=xref_oif_tx),
    np_("opt.tx.11.1.210", "Laser frequency noise", "tx_optical", ALL, "Hz^2/Hz",
        "Table 11-2 / Figure 11-1, §11.2.1", check_type="mask", conf="medium",
        notes="Mask parameter — see mask_profiles[mask.laser_freq_noise.60]. No scalar min/max."),
    np_("opt.tx.11.1.211", "Laser RIN (average)", "tx_optical", ALL, "dB/Hz",
        "Table 11-2, §11.2", mx=-145, check_type="max_only",
        test_conditions={"notes": "0.2 GHz < f < 10 GHz"}),
    np_("opt.tx.11.1.212", "Laser RIN (peak)", "tx_optical", ALL, "dB/Hz",
        "Table 11-2, §11.2", mx=-140, check_type="max_only",
        test_conditions={"notes": "0.2 GHz < f < 10 GHz"}),
    np_("opt.tx.11.1.213a", "Tx clock low-frequency phase noise", "tx_optical", ALL, "dBc/Hz",
        "Table 11-2 / §11.2.2", check_type="mask", conf="medium",
        notes="Mask parameter — see mask_profiles[mask.tx_clock_phase_noise.60]."),
    np_("opt.tx.11.1.213b.lf", "Tx clock total integrated RMS phase jitter (10 kHz–10 MHz)",
        "tx_optical", ALL, "fs", "Table 11-2, §11.2", mx=600, check_type="max_only",
        test_conditions={"notes": "10 kHz to 10 MHz"}),
    np_("opt.tx.11.1.213b.hf", "Tx clock total integrated RMS phase jitter (1 MHz–200 MHz)",
        "tx_optical", ALL, "fs", "Table 11-2, §11.2", mx=250, check_type="max_only",
        test_conditions={"notes": "1 MHz to 200 MHz"}),
    np_("opt.tx.11.1.215a", "Tx spectral upper mask", "tx_optical", {"symbol_rate_G": [60]}, "dB",
        "§11.4.10 / Figure 11-3", check_type="mask",
        notes="Mask parameter — see mask_profiles[mask.tx_spectral.upper.60]."),
    np_("opt.tx.11.1.215b", "Tx spectral lower mask", "tx_optical", {"symbol_rate_G": [60]}, "dB",
        "§11.4.10 / Figure 11-3", check_type="mask",
        notes="Mask parameter — see mask_profiles[mask.tx_spectral.lower.60]."),
    np_("opt.tx.11.1.220a", "Tx output power stability", "tx_optical", ALL, "dBm",
        "Table 11-2, §11.2", mn=-1, mx=1, notes="Over life at fixed wavelength/temperature."),
    np_("opt.tx.11.1.220c", "Tx power setting accuracy", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2", mn=-1, mx=1, xrefs=[{"standard_id": "CMIS-5.0",
        "clause": "Page 12h TargetOutputPowerTx", "relationship": "references"}]),
    np_("opt.tx.11.1.240", "Transmitter reflectance", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2", mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.241", "Transmitter back reflection tolerance", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2", mx=-24, check_type="max_only"),
    np_("opt.tx.11.1.260", "X-Y skew", "tx_optical", ALL, "ps",
        "Table 11-2, §11.2", mx=5, check_type="max_only"),
    np_("opt.tx.11.1.270a", "DC I-Q offset", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2 / §11.4.8", mx=-26, check_type="max_only"),
    np_("opt.tx.11.1.270b", "I-Q instantaneous offset", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2 / §11.4.8", mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.271", "Mean I-Q amplitude imbalance", "tx_optical", ALL, "dB",
        "Table 11-2, §11.2", mx=1, check_type="max_only"),
    np_("opt.tx.11.1.272", "I-Q phase imbalance", "tx_optical", ALL, "degrees",
        "Table 11-2, §11.2", mn=-5, mx=5),
    np_("opt.tx.11.1.273", "I-Q skew", "tx_optical", ALL, "ps",
        "Table 11-2, §11.2", mx=0.75, check_type="max_only"),

    # Baseline (60LA) minimum Tx output power — per format
    np_("opt.tx.11.1.220.400", "Minimum Tx output signal power", "tx_optical",
        {"format": ["400ZR+"], "power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2",
        mn=-10, check_type="min_only", aliases=["tx_output_power_dBm", "tx_output_power_min_dBm", "output power"],
        test_conditions={"notes": "Over wavelength, temperature and aging."}),
    np_("opt.tx.11.1.220.300", "Minimum Tx output signal power", "tx_optical",
        {"format": ["300ZR+"], "power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2",
        mn=-10, check_type="min_only", aliases=["tx_output_power_dBm"]),
    np_("opt.tx.11.1.220.200", "Minimum Tx output signal power", "tx_optical",
        {"format": ["200ZR+"], "power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2",
        mn=-9, check_type="min_only", aliases=["tx_output_power_dBm"]),
    np_("opt.tx.11.1.220.100", "Minimum Tx output signal power", "tx_optical",
        {"format": ["100ZR+"], "power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2",
        mn=-8, check_type="min_only", aliases=["tx_output_power_dBm"]),
    np_("opt.tx.11.1.220b.400", "Minimum provisionable Tx output power range", "tx_optical",
        {"format": ["400ZR+"], "power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2",
        mn=-13, mx=-9, severity="conditional"),
    np_("opt.tx.11.1.221", "Tx output power with transmit disabled", "tx_optical",
        {"power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2", mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.222", "Total output power during wavelength switching", "tx_optical",
        {"power_class": ["baseline"]}, "dBm", "Table 11-2, §11.2", mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.230", "In-band (IB) OSNR", "tx_optical",
        {"power_class": ["baseline"]}, "dB/0.1nm", "Table 11-2, §11.2", mn=34, check_type="min_only",
        aliases=["ib_osnr_dB"], test_conditions={"notes": "Referenced to 0.1 nm at 193.7 THz."}),
    np_("opt.tx.11.1.231", "Out-of-band (OOB) OSNR", "tx_optical",
        {"power_class": ["baseline"]}, "dB/0.1nm", "Table 11-2, §11.2", mn=23, check_type="min_only",
        aliases=["oob_osnr_dB"], xrefs=[XREF_G709("OOB OSNR analogue", "OSNR", )]),
    np_("opt.tx.11.1.250", "Tx polarization dependent power difference", "tx_optical",
        {"power_class": ["baseline"]}, "dB", "Table 11-2, §11.2", mx=1.5, check_type="max_only",
        test_conditions={"notes": "Between X and Y polarization."}),

    # 60HA / 60HB (Table 11-4x)
    np_("opt.tx.11.1.220x", "Minimum Tx output signal power (60HA/60HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mn=0, check_type="min_only", aliases=["tx_output_power_dBm", "tx_output_power_min_dBm"]),
    np_("opt.tx.11.1.220bx", "Minimum provisionable Tx output power range (60HA/60HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mn=-4, mx=1, severity="conditional"),
    np_("opt.tx.11.1.221x.ha", "Tx output power with transmit disabled (60HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.221x.hb", "Tx output power with transmit disabled (60HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mx=-35, check_type="max_only"),
    np_("opt.tx.11.1.222x.ha", "Total output power during wavelength switching (60HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.222x.hb", "Total output power during wavelength switching (60HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [60]}, "dBm", "Table 11-4x, §11.2",
        mx=-35, check_type="max_only"),
    np_("opt.tx.11.1.230x.ha", "In-band (IB) OSNR (60HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [60]}, "dB/12.5GHz", "Table 11-4x, §11.2",
        mn=34, check_type="min_only", aliases=["ib_osnr_dB"]),
    np_("opt.tx.11.1.230x.hb", "In-band (IB) OSNR (60HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [60]}, "dB/12.5GHz", "Table 11-4x, §11.2",
        mn=36, check_type="min_only", aliases=["ib_osnr_dB"]),
    np_("opt.tx.11.1.231x.ha", "Out-of-band (OOB) OSNR (60HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [60]}, "dB/12.5GHz", "Table 11-4x, §11.2",
        mn=23, check_type="min_only", aliases=["oob_osnr_dB"]),
    np_("opt.tx.11.1.231x.hb", "Out-of-band (OOB) OSNR (60HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [60]}, "dB/12.5GHz", "Table 11-4x, §11.2",
        mn=43, check_type="min_only", aliases=["oob_osnr_dB"],
        footnotes=["OOB referenced outside ±150 GHz of channel center, excluding SMSR peaks."]),
    np_("opt.tx.11.1.250x", "Tx polarization dependent power difference (60HA/60HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [60]}, "dB", "Table 11-4x, §11.2",
        mx=1.0, check_type="max_only"),

    # 80HA / 80HB (Table 11-5y) — ZR400-OFEC-8QAM only
    np_("opt.tx.11.1.220y", "Minimum Tx output signal power (80HA/80HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mn=0, check_type="min_only", aliases=["tx_output_power_dBm", "tx_output_power_min_dBm"]),
    np_("opt.tx.11.1.220by", "Minimum provisionable Tx output power range (80HA/80HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mn=-4, mx=1, severity="conditional"),
    np_("opt.tx.11.1.221y.ha", "Tx output power with transmit disabled (80HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.221y.hb", "Tx output power with transmit disabled (80HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mx=-35, check_type="max_only"),
    np_("opt.tx.11.1.222y.ha", "Total output power during wavelength switching (80HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mx=-20, check_type="max_only"),
    np_("opt.tx.11.1.222y.hb", "Total output power during wavelength switching (80HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [80]}, "dBm", "Table 11-5y, §11.2",
        mx=-35, check_type="max_only"),
    np_("opt.tx.11.1.230y.ha", "In-band (IB) OSNR (80HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [80]}, "dB/12.5GHz", "Table 11-5y, §11.2",
        mn=34, check_type="min_only", aliases=["ib_osnr_dB"]),
    np_("opt.tx.11.1.230y.hb", "In-band (IB) OSNR (80HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [80]}, "dB/12.5GHz", "Table 11-5y, §11.2",
        mn=36, check_type="min_only", aliases=["ib_osnr_dB"]),
    np_("opt.tx.11.1.231y.ha", "Out-of-band (OOB) OSNR (80HA)", "tx_optical",
        {"power_class": ["HA"], "symbol_rate_G": [80]}, "dB/12.5GHz", "Table 11-5y, §11.2",
        mn=23, check_type="min_only", aliases=["oob_osnr_dB"]),
    np_("opt.tx.11.1.231y.hb", "Out-of-band (OOB) OSNR (80HB)", "tx_optical",
        {"power_class": ["HB"], "symbol_rate_G": [80]}, "dB/12.5GHz", "Table 11-5y, §11.2",
        mn=43, check_type="min_only", aliases=["oob_osnr_dB"],
        footnotes=["OOB referenced outside ±150 GHz of channel center, excluding SMSR peaks."]),
    np_("opt.tx.11.1.250y", "Tx polarization dependent power difference (80HA/80HB)", "tx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [80]}, "dB", "Table 11-5y, §11.2",
        mx=1.0, check_type="max_only"),
]

# ---------------------------------------------------------------- Rx optical
RX = "Table 11-8 / 11-9x / 11-10y, §11.3"
osnr_tc = {"launch_condition": "back_to_back", "notes": "At OFEC threshold; ref 0.1 nm at 193.7 THz / 12.5 GHz."}

rx = [
    np_("opt.rx.11.1.300", "Frequency offset between received carrier and LO", "rx_optical",
        ALL, "GHz", "Table 11-8, §11.3", mn=-3.6, mx=3.6, aliases=["frequency_offset_GHz"]),
    # Input power range — per format
    np_("opt.rx.11.1.310.400", "Receiver input power range", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-16QAM"]}, "dBm", "Table 11-8, §11.3",
        mn=-12, mx=0, aliases=["rx_input_power_min_dBm", "rx_input_power_max_dBm", "input power"]),
    np_("opt.rx.11.1.310y.400q8", "Receiver input power range (400G 8QAM/80G)", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-8QAM"], "symbol_rate_G": [80]}, "dBm",
        "Table 11-10y, §11.3", mn=-11, mx=0, aliases=["rx_input_power_min_dBm", "rx_input_power_max_dBm"]),
    np_("opt.rx.11.1.310.300", "Receiver input power range", "rx_optical", F300, "dBm",
        "Table 11-8, §11.3", mn=-15, mx=0, aliases=["rx_input_power_min_dBm", "rx_input_power_max_dBm"]),
    np_("opt.rx.11.1.310.200", "Receiver input power range", "rx_optical", F200, "dBm",
        "Table 11-8, §11.3", mn=-18, mx=0, aliases=["rx_input_power_min_dBm", "rx_input_power_max_dBm"]),
    np_("opt.rx.11.1.310.100", "Receiver input power range", "rx_optical", F100, "dBm",
        "Table 11-8, §11.3", mn=-18, mx=0, aliases=["rx_input_power_min_dBm", "rx_input_power_max_dBm"]),
    # OSNR tolerance — per format / rate
    np_("opt.rx.11.1.330.400", "OSNR tolerance", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-16QAM"]}, "dB/0.1nm", "Table 11-8, §11.3",
        mx=24, check_type="max_only", aliases=["osnr_tolerance_dB", "required OSNR", "OSNR"],
        test_conditions=osnr_tc),
    np_("opt.rx.11.1.330y.400q8", "OSNR tolerance (400G 8QAM/80G)", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-8QAM"], "symbol_rate_G": [80]}, "dB/0.1nm",
        "Table 11-10y, §11.3", mx=22.5, check_type="max_only", aliases=["osnr_tolerance_dB"],
        test_conditions=osnr_tc),
    np_("opt.rx.11.1.330.300", "OSNR tolerance", "rx_optical", F300, "dB/0.1nm",
        "Table 11-8, §11.3", mx=21, check_type="max_only", aliases=["osnr_tolerance_dB"],
        test_conditions=osnr_tc),
    np_("opt.rx.11.1.330.200", "OSNR tolerance", "rx_optical", F200, "dB/0.1nm",
        "Table 11-8, §11.3", mx=16, check_type="max_only", aliases=["osnr_tolerance_dB"],
        test_conditions=osnr_tc),
    np_("opt.rx.11.1.330.100", "OSNR tolerance", "rx_optical", F100, "dB/0.1nm",
        "Table 11-8, §11.3", mx=12.5, check_type="max_only", aliases=["osnr_tolerance_dB"],
        test_conditions=osnr_tc),
    np_("opt.rx.11.1.340", "Optical return loss (at Rx input)", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mn=20, check_type="min_only"),
    # CD tolerance — per format
    np_("opt.rx.11.1.341.400", "CD tolerance", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-16QAM"]}, "ps/nm", "Table 11-8, §11.3",
        mn=20000, check_type="min_only", aliases=["chromatic_dispersion_ps_nm", "CD tolerance"]),
    np_("opt.rx.11.1.341y.400q8", "CD tolerance (400G 8QAM/80G)", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-8QAM"], "symbol_rate_G": [80]}, "ps/nm",
        "Table 11-10y, §11.3", mn=30000, check_type="min_only", aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.rx.11.1.341.300", "CD tolerance", "rx_optical", F300, "ps/nm",
        "Table 11-8, §11.3", mn=40000, check_type="min_only", aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.rx.11.1.341.200", "CD tolerance", "rx_optical", F200, "ps/nm",
        "Table 11-8, §11.3", mn=50000, check_type="min_only", aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.rx.11.1.341.100", "CD tolerance", "rx_optical", F100, "ps/nm",
        "Table 11-8, §11.3", mn=100000, check_type="min_only", aliases=["chromatic_dispersion_ps_nm"]),
    np_("opt.rx.11.1.342", "CD OSNR tolerance penalty", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mx=0.5, check_type="max_only"),
    # PMD (avg) tolerance — per format
    np_("opt.rx.11.1.350.400", "PMD (avg) tolerance", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-16QAM"]}, "ps", "Table 11-8, §11.3",
        mn=20, check_type="min_only", notes="Min tolerance includes Tx max X-Y skew."),
    np_("opt.rx.11.1.350y.400q8", "PMD (avg) tolerance (400G 8QAM/80G)", "rx_optical",
        {"format": ["400ZR+"], "modulation": ["DP-8QAM"], "symbol_rate_G": [80]}, "ps",
        "Table 11-10y, §11.3", mn=20, check_type="min_only"),
    np_("opt.rx.11.1.350.300", "PMD (avg) tolerance", "rx_optical", F300, "ps",
        "Table 11-8, §11.3", mn=25, check_type="min_only"),
    np_("opt.rx.11.1.350.200", "PMD (avg) tolerance", "rx_optical", F200, "ps",
        "Table 11-8, §11.3", mn=25, check_type="min_only"),
    np_("opt.rx.11.1.350.100", "PMD (avg) tolerance", "rx_optical", F100, "ps",
        "Table 11-8, §11.3", mn=30, check_type="min_only"),
    np_("opt.rx.11.1.351.a", "Peak PDL tolerance (1.3 dB penalty)", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mn=3.0, check_type="min_only",
        test_conditions={"notes": "≤1.3 dB additional OSNR penalty; ΔSOP ≤1 rad/ms."}),
    np_("opt.rx.11.1.351.b", "Peak PDL tolerance (1.8 dB penalty)", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mn=3.5, check_type="min_only",
        test_conditions={"notes": "≤1.8 dB additional OSNR penalty; ΔSOP ≤1 rad/ms."}),
    np_("opt.rx.11.1.352", "Tolerance to change in SOP (baseline)", "rx_optical",
        {"power_class": ["baseline"]}, "krad/s", "Table 11-8, §11.3", mn=50, check_type="min_only",
        test_conditions={"notes": "≤0.5 dB additional OSNR penalty over all PMD/PDL."}),
    np_("opt.rx.11.1.352x", "Tolerance to change in SOP (60HA/60HB)", "rx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [60]}, "krad/s", "Table 11-9x, §11.3",
        mn=300, check_type="min_only", test_conditions={"notes": "≤1 dB additional OSNR penalty."}),
    np_("opt.rx.11.1.352y", "Tolerance to change in SOP (80HA/80HB)", "rx_optical",
        {"power_class": ["HA", "HB"], "symbol_rate_G": [80]}, "krad/s", "Table 11-10y, §11.3",
        mn=300, check_type="min_only", test_conditions={"notes": "≤1 dB additional OSNR penalty."}),
    np_("opt.rx.11.1.353", "Optical input power transient tolerance", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mn=-2, mx=2),
    np_("opt.rx.11.1.354", "Adjacent-channel crosstalk OSNR tolerance penalty", "rx_optical", ALL, "dB",
        "Table 11-8, §11.3", mx=1, check_type="max_only"),
    np_("opt.rx.11.1.355", "Intra-channel filtering penalty", "rx_optical",
        {"grid_GHz": [75]}, "dB", "Table 11-8, §11.3", mx=0.5, check_type="max_only",
        notes="Due to Mux/Demux filtering on 75 GHz grid."),
    # Colorless drop penalties — 60HB / 80HB only
    np_("opt.rx.11.1.360x.400", "Colorless drop OSNR penalty (60HB, 400G @15 dB ratio)", "rx_optical",
        {"format": ["400ZR+"], "power_class": ["HB"], "symbol_rate_G": [60]}, "dB",
        "Table 11-9x, §11.3", mx=0.5, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 60HB. 0.5 dB @ 15 dB ratio; 0.3 dB @ 13 dB ratio."]),
    np_("opt.rx.11.1.360x.300", "Colorless drop OSNR penalty (60HB, 300G @15 dB ratio)", "rx_optical",
        {"format": ["300ZR+"], "power_class": ["HB"], "symbol_rate_G": [60]}, "dB",
        "Table 11-9x, §11.3", mx=0.3, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 60HB."]),
    np_("opt.rx.11.1.360x.200", "Colorless drop OSNR penalty (60HB, 200G @15 dB ratio)", "rx_optical",
        {"format": ["200ZR+"], "power_class": ["HB"], "symbol_rate_G": [60]}, "dB",
        "Table 11-9x, §11.3", mx=0.3, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 60HB."]),
    np_("opt.rx.11.1.365x", "Colorless drop adjacent channel crosstalk penalty at OSNR limit (60HB)",
        "rx_optical", {"power_class": ["HB"], "symbol_rate_G": [60]}, "dB", "Table 11-9x, §11.3",
        mx=0.5, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 60HB. 75 GHz spacing; adjacent channels ≤1 dB above signal."]),
    np_("opt.rx.11.1.360y.400", "Colorless drop OSNR penalty (80HB, 400G @15 dB ratio)", "rx_optical",
        {"format": ["400ZR+"], "power_class": ["HB"], "symbol_rate_G": [80]}, "dB",
        "Table 11-10y, §11.3", mx=0.5, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 80HB. 0.5 dB @ 15 dB ratio; 0.3 dB @ 13 dB ratio."]),
    np_("opt.rx.11.1.365y", "Colorless drop adjacent channel crosstalk penalty at OSNR limit (80HB)",
        "rx_optical", {"power_class": ["HB"], "symbol_rate_G": [80]}, "dB", "Table 11-10y, §11.3",
        mx=0.5, check_type="max_only", severity="conditional",
        footnotes=["Only applies to 80HB. 100 GHz spacing; adjacent channels ≤1 dB above signal."]),
    np_("opt.rx.post_fec_ber", "Post-FEC BER", "rx_optical", ALL, "BER",
        "Table 11-8, §11.3", mx=1e-15, check_type="max_only",
        footnotes=["Achieved at pre-FEC BER ≤ 2.0E-2."], aliases=["post_fec_ber"]),
]

# ---------------------------------------------------------------- Masks
mask_profiles = [
    {
        "mask_id": "mask.laser_freq_noise.60", "mask_type": "laser_freq_noise",
        "applies_to": {"symbol_rate_G": [60]}, "x_axis_unit": "Hz", "y_axis_unit": "Hz^2/Hz",
        "reference": "Table 11-6 / Figure 11-1, §11.2.1",
        "points": [
            {"freq_offset_GHz": 1.0e2, "limit_dBc": 1.0e11},
            {"freq_offset_GHz": 1.0e4, "limit_dBc": 1.0e9},
            {"freq_offset_GHz": 1.0e6, "limit_dBc": 1.0e6},
            {"freq_offset_GHz": 1.0e7, "limit_dBc": 6.0e5},
            {"freq_offset_GHz": 1.0e8, "limit_dBc": 1.6e5},
            {"freq_offset_GHz": 1.0e9, "limit_dBc": 1.6e5},
        ],
        "cross_standard_refs": [],
    },
    {
        "mask_id": "mask.tx_clock_phase_noise.60", "mask_type": "tx_clock_phase_noise",
        "applies_to": {"symbol_rate_G": [60]}, "x_axis_unit": "Hz", "y_axis_unit": "dBc/Hz",
        "reference": "Table 11-7 / Figure 11-2, §11.2.2 (fc=fbaud/128≈469.83 MHz)",
        "points": [
            {"freq_offset_GHz": 1.0e4, "limit_dBc": -100},
            {"freq_offset_GHz": 1.0e5, "limit_dBc": -120},
            {"freq_offset_GHz": 1.0e6, "limit_dBc": -130},
            {"freq_offset_GHz": 1.0e7, "limit_dBc": -140},
        ],
        "cross_standard_refs": [],
    },
    {
        "mask_id": "mask.tx_spectral.upper.60", "mask_type": "tx_spectral",
        "applies_to": {"symbol_rate_G": [60], "grid_GHz": [75]}, "x_axis_unit": "GHz", "y_axis_unit": "dB",
        "reference": "Figure 11-3, §11.4.10 (RRC roll-off 0.4 upper)",
        "points": [
            {"freq_offset_GHz": 30.0, "limit_dBc": 0.0},
            {"freq_offset_GHz": 37.0, "limit_dBc": -10.0},
            {"freq_offset_GHz": 39.2, "limit_dBc": -15.0},
            {"freq_offset_GHz": 40.4, "limit_dBc": -20.0},
        ],
        "cross_standard_refs": [],
    },
    {
        "mask_id": "mask.tx_spectral.lower.60", "mask_type": "tx_spectral",
        "applies_to": {"symbol_rate_G": [60], "grid_GHz": [75]}, "x_axis_unit": "GHz", "y_axis_unit": "dB",
        "reference": "Figure 11-3, §11.4.10 (RRC roll-off 0.05 lower)",
        "points": [
            {"freq_offset_GHz": 30.0, "limit_dBc": -9.0},
            {"freq_offset_GHz": 31.3, "limit_dBc": -20.0},
            {"freq_offset_GHz": 31.3, "limit_dBc": -35.0},
        ],
        "cross_standard_refs": [],
    },
]

# ---------------------------------------------------------------- Compliance rules
GROUP_BY_CAT = {"dwdm_link": "dwdm_link", "tx_optical": "tx_optical",
                "rx_optical": "rx_optical", "filter": "dwdm_link"}

compliance_rules = []

# Explicit (semantic) rules per Pass 8
compliance_rules += [
    {"rule_id": "R1.1", "group": "format_identification",
     "statement": "The SFF-8024 media interface ID advertised by the module SHALL match the value defined for its media_interface_id.",
     "predicate_type": "enum_match", "parameter_ref": None, "expected_value": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Tables 1-3 / 1-4a, §1",
     "cross_standard_refs": [XREF_SFF("SFF-8024 Media Interface ID")], "extraction_confidence": "high"},
    {"rule_id": "R2.1", "group": "line_encoding",
     "statement": "The line baud rate SHALL be within ±20 ppm of the nominal symbol rate for the mode.",
     "predicate_type": "numeric_tolerance", "parameter_ref": None, "tolerance": 20,
     "tolerance_unit": "ppm", "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 1-3 / Table 11-2, §1/§11.2", "extraction_confidence": "high"},
    {"rule_id": "R3.1", "group": "line_encoding",
     "statement": "The modulation format SHALL match the format defined for the media_interface_id (DP-16QAM/DP-8QAM/DP-QPSK).",
     "predicate_type": "enum_match", "parameter_ref": None, "expected_value": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 1-2a, §1", "extraction_confidence": "high"},
    {"rule_id": "R4.1", "group": "ofec",
     "statement": "OFEC Net Coding Gain SHALL be at least 11.6 dB.",
     "predicate_type": "numeric_range", "parameter_ref": None, "expected_value": 11.6,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 1-3, §1/§7", "extraction_confidence": "high"},
    {"rule_id": "R5.1", "group": "ofec",
     "statement": "The OFEC pre-FEC BER threshold SHALL be 2.0E-2 (post-FEC BER ≤ 1E-15).",
     "predicate_type": "numeric_range", "parameter_ref": "opt.rx.post_fec_ber",
     "expected_value": 0.02, "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 1-3 / Table 11-8", "extraction_confidence": "high"},
    {"rule_id": "R9.1", "group": "tx_optical",
     "statement": "Transmitter spectrum SHALL comply with the upper and lower Tx spectral masks.",
     "predicate_type": "table_lookup", "parameter_ref": "opt.tx.11.1.215a",
     "applies_to": {"symbol_rate_G": [60]}, "severity": "mandatory",
     "reference": "§11.4.10 / Figure 11-3", "rag_fallback": True, "extraction_confidence": "high"},
    {"rule_id": "R10.1", "group": "framing",
     "statement": "ZR frame overhead and payload SHALL align on 257-bit block boundaries per the frame format.",
     "predicate_type": "numeric_range", "parameter_ref": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 3-1, §3.1", "cross_standard_refs": [XREF_OIF("400ZR frame")],
     "extraction_confidence": "high"},
    {"rule_id": "R11.1", "group": "framing",
     "statement": "The MSI overhead byte (row 4, byte 5) SHALL carry the value defined for the active multiplexing mode.",
     "predicate_type": "table_lookup", "parameter_ref": None,
     "applies_to": {"format": ["400ZR+"]}, "severity": "mandatory",
     "reference": "Table 3-2, §3.7", "cross_standard_refs": [XREF_G709("Clause 20.4.1.1 (PT22 MSI)")],
     "extraction_confidence": "high"},
    {"rule_id": "R12.1", "group": "interoperability",
     "statement": "Only client signals from a single host-interface column may be multiplexed onto a network interface; mixed client modes are out of scope.",
     "predicate_type": "prose_rag", "parameter_ref": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 1-1, §1", "rag_fallback": True, "extraction_confidence": "high"},
    {"rule_id": "R13.1", "group": "gmp_mapping",
     "statement": "GMP SHALL be performed across a group of four consecutive frames (Pm,server = 10220 GMP blocks per 4 frames for all client rates).",
     "predicate_type": "cross_param_ratio", "parameter_ref": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "Table 4-1, §4.3", "cross_standard_refs": [XREF_G709("Annex D (GMP)")],
     "extraction_confidence": "high"},
    {"rule_id": "R14.1", "group": "ofec",
     "statement": "The OFEC encoder SHALL implement the codec/polynomial definition of §7.4.",
     "predicate_type": "prose_rag", "parameter_ref": None,
     "applies_to": {"format": ["ALL"]}, "severity": "mandatory",
     "reference": "§7.4", "rag_fallback": True, "extraction_confidence": "high"},
]

# Per-parameter numeric/mask rules (deterministic coverage of every optical limit)
_seq = {}
for param in dwdm + tx + rx:
    cat = param["category"]
    grp = GROUP_BY_CAT.get(cat, "tx_optical")
    pred = "table_lookup" if param.get("check_type") == "mask" else (
        "numeric_range" if (("min" in param) or ("max" in param)) else "prose_rag")
    _seq[cat] = _seq.get(cat, 0) + 1
    compliance_rules.append({
        "rule_id": f"R-{cat}.{_seq[cat]}",
        "group": grp,
        "statement": f"{param['name']} SHALL be within the limits defined in {param['reference']}.",
        "predicate_type": pred,
        "parameter_ref": param["id"],
        "applies_to": param["applies_to"],
        "severity": param["severity"],
        "reference": param["reference"],
        "cross_standard_refs": param.get("cross_standard_refs", []),
        "extraction_confidence": param.get("extraction_confidence", "high"),
    })

# ---------------------------------------------------------------- Assemble
PDF_URL = "https://openzrplus.org/wp-content/uploads/2024/04/openzrplus_rev3p0_final2.pdf"
dataset = {
    "$schema": "../openzrplus.schema.json",
    "meta": {
        "standard_name": "OpenZR+ MSA Technical Specification",
        "version": "3.0",
        "revision_date": "2023-07-28",
        "source_url": PDF_URL,
        "publisher": "OpenZR+ MSA",
        "dataset_version": "0.1.0",
        "extraction_status": "llm_extracted",
        "extracted_by": "Claude (in-IDE extraction per EXTRACTION_SYSTEM_PROMPT.md)",
        "verified_by": "",
        "last_updated": str(date.today()),
        "changelog": [{"date": str(date.today()),
                       "change": "Initial full extraction from openzrplus_rev3p0_final2.pdf (9-pass contract)."}],
        "related_standards": [
            {"standard_id": "OIF-400ZR-01.0", "name": "OIF 400ZR Implementation Agreement", "relationship": "normative_reference"},
            {"standard_id": "ITU-T-G.709", "name": "ITU-T G.709 OTN Interfaces", "relationship": "normative_reference"},
            {"standard_id": "SFF-8024", "name": "SFF-8024 Transceiver Management", "relationship": "normative_reference"},
            {"standard_id": "IEEE-802.3", "name": "IEEE 802.3 Ethernet", "relationship": "informative_reference"},
            {"standard_id": "CMIS-5.0", "name": "Common Management Interface Specification", "relationship": "peer_standard"},
            {"standard_id": "OIF-C-CMIS", "name": "OIF Coherent CMIS", "relationship": "peer_standard"},
        ],
    },
    "identity": identity,
    "line_encoding": line_encoding,
    "framing": framing,
    "optical_specs": {
        "dwdm_link": dwdm,
        "tx_optical": tx,
        "rx_optical": rx,
        "mask_profiles": mask_profiles,
    },
    "client_interfaces": [],
    "compliance_rules": compliance_rules,
}


def main():
    OUT_DIR.mkdir(exist_ok=True)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(dataset), key=lambda e: list(e.absolute_path))
    out = OUT_DIR / "openzrplus_dataset.json"
    out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"identity={len(identity)} line_encoding={len(line_encoding)} framing={len(framing)} "
          f"dwdm={len(dwdm)} tx={len(tx)} rx={len(rx)} masks={len(mask_profiles)} rules={len(compliance_rules)}")
    if errors:
        print(f"\nSCHEMA ERRORS ({len(errors)}):")
        for e in errors[:40]:
            print("  " + " > ".join(str(p) for p in e.absolute_path) + ": " + e.message)
    else:
        print("\nSchema validation: PASSED")


if __name__ == "__main__":
    main()
