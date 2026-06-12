#!/usr/bin/env python3
"""
OpenZR+ MSA Extraction Pipeline
================================
Drives the 9-pass LLM extraction from the OpenZR+ PDF, assembles the dataset,
and validates it against the JSON schema.

Usage:
    pip install anthropic pdfplumber jsonschema
    python extract_pipeline.py --pdf openzrplus_rev3p0_final2.pdf

Cursor: Run this from the project root. Set ANTHROPIC_API_KEY in your env.
        Outputs go to ./output/openzrplus_dataset.json
"""

import os
import re
import json
import time
import logging
import argparse
import hashlib
from pathlib import Path
from datetime import date

import anthropic
import pdfplumber
import jsonschema
import pymupdf4llm


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL              = "claude-opus-4-6"   # Use Opus for extraction — accuracy > cost here
MAX_TOKENS         = 8192

# Resolve all project paths relative to the repository root (parent of scripts/)
# so the pipeline runs identically regardless of the current working directory.
PROJECT_ROOT       = Path(__file__).resolve().parent.parent
OUTPUT_DIR         = PROJECT_ROOT / "output"
SCHEMA_PATH        = PROJECT_ROOT / "openzrplus.schema.json"
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "prompts" / "EXTRACTION_SYSTEM_PROMPT.md"
PASSES_PATH        = PROJECT_ROOT / "prompts" / "EXTRACTION_PASSES.md"
CACHE_DIR          = PROJECT_ROOT / ".extraction_cache"  # Resume interrupted runs

PDF_URL = "https://openzrplus.org/wp-content/uploads/2024/04/openzrplus_rev3p0_final2.pdf"

# Page ranges for each extraction pass (0-indexed, inclusive)
# Adjust if the PDF pagination changes between downloads.
PASS_PAGE_RANGES = {
    "identity":          (5,  9),   # §1, Tables 1-2a/1-3/1-4a
    "line_encoding":     (5,  9),   # §1 + §7 §8 combined
    "framing":           (11, 22),  # §3, §4, §5
    "dwdm_link":         (61, 64),  # §11.1, Table 11-1
    "tx_optical":        (63, 70),  # §11.2, Tables 11-2/11-2a
    "rx_optical":        (70, 74),  # §11.3, Table 11-3
    "mask_profiles":     (67, 78),  # §11.2.1/11.2.2/11.4.10/11.4.11
    "compliance_rules":  (0,  88),  # Full doc — derived rules
    "gap_check":         (0,  88),  # Full doc — verification pass
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf_pages(pdf_path: Path, start_page: int, end_page: int) -> str:
    """Extract text from a page range using pdfplumber. Falls back to raw text."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[start_page : end_page + 1]
        for page in pages:
            # Try table extraction first — pdfplumber renders tables as TSV
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [cell or "" for cell in row]
                        text_parts.append("\t".join(cleaned))
                    text_parts.append("")

            # Always also extract plain text (catches prose around tables)
            raw = page.extract_text(x_tolerance=2, y_tolerance=2)
            if raw:
                text_parts.append(raw)
            text_parts.append(f"\n--- PAGE {start_page + pages.index(page) + 1} ---\n")

    return "\n".join(text_parts)

    
def extract_pdf_pages_with_pymupdf4llm(pdf_path: Path) -> str:
    return pymupdf4llm.to_markdown(str(pdf_path))

    
def get_headings_from_md(markdown_text):
    # Re.M (re.MULTILINE) forces ^ to match the start of each line
    matches = re.findall(r'^(#{1,6})\s+(.+)$', markdown_text, re.M)
    return [(len(level), text) for level, text in matches]

# ---------------------------------------------------------------------------
# Cache helpers (allows resuming interrupted runs)
# ---------------------------------------------------------------------------

def cache_key(pass_name: str, text_hash: str) -> str:
    return hashlib.sha256(f"{pass_name}:{text_hash}".encode()).hexdigest()[:16]

def load_cache(pass_name: str, text_hash: str) -> dict | None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{cache_key(pass_name, text_hash)}.json"
    if path.exists():
        log.info(f"  Cache hit for pass '{pass_name}'")
        return json.loads(path.read_text())
    return None

def save_cache(pass_name: str, text_hash: str, result: dict):
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{cache_key(pass_name, text_hash)}.json"
    path.write_text(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text()

def load_pass_prompt(pass_name: str) -> str:
    """Extract the user prompt block for a given pass from EXTRACTION_PASSES.md."""
    content = PASSES_PATH.read_text()

    # Map pass names to the Pass N heading in the markdown
    heading_map = {
        "identity":         "Pass 1",
        "line_encoding":    "Pass 2",
        "framing":          "Pass 3",
        "dwdm_link":        "Pass 4",
        "tx_optical":       "Pass 5",
        "rx_optical":       "Pass 6",
        "mask_profiles":    "Pass 7",
        "compliance_rules": "Pass 8",
        "gap_check":        "Pass 9",
    }

    heading = heading_map[pass_name]
    # Extract the code block (triple-backtick) after the heading
    pattern = rf"## {heading}.*?```\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find prompt for pass '{pass_name}' in {PASSES_PATH}")
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# LLM call with retry
# ---------------------------------------------------------------------------

def call_llm(client: anthropic.Anthropic, system: str, user: str,
             pass_name: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            log.info(f"  Calling API (attempt {attempt + 1}/{retries})…")
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = resp.content[0].text.strip()

            # Strip accidental markdown fences
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            parsed = json.loads(raw)
            return parsed

        except json.JSONDecodeError as e:
            log.warning(f"  JSON parse error on attempt {attempt + 1}: {e}")
            if attempt == retries - 1:
                # Save raw for debug
                debug_path = OUTPUT_DIR / f"debug_{pass_name}_raw.txt"
                debug_path.write_text(raw)
                log.error(f"  Raw output saved to {debug_path}")
                raise
            time.sleep(2 ** attempt)

        except anthropic.APIError as e:
            log.warning(f"  API error on attempt {attempt + 1}: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


# ---------------------------------------------------------------------------
# Individual pass runner
# ---------------------------------------------------------------------------

def run_pass(client: anthropic.Anthropic, pass_name: str,
             pdf_path: Path, system_prompt: str) -> dict:

    log.info(f"Pass: {pass_name}")
    start, end = PASS_PAGE_RANGES[pass_name]

    # Extract PDF text
    log.info(f"  Extracting pages {start+1}–{end+1} from PDF…")
    pdf_text = extract_pdf_pages(pdf_path, start, end)
    text_hash = hashlib.sha256(pdf_text.encode()).hexdigest()[:12]

    # Check cache
    cached = load_cache(pass_name, text_hash)
    if cached is not None:
        return cached

    # Build user message
    pass_prompt = load_pass_prompt(pass_name)
    user_message = f"""
## Standard text (pages {start+1}–{end+1})

{pdf_text}

---

## Your task

{pass_prompt}
""".strip()

    # Call LLM
    log.info(f"  Sending {len(pdf_text):,} chars to {MODEL}…")
    result = call_llm(client, system_prompt, user_message, pass_name)

    # Cache result
    save_cache(pass_name, text_hash, result)
    log.info(f"  Done. Keys returned: {list(result.keys())}")
    return result


# ---------------------------------------------------------------------------
# Gap check pass (needs both full text AND assembled dataset)
# ---------------------------------------------------------------------------

def run_gap_check(client: anthropic.Anthropic, pdf_path: Path,
                  dataset: dict, system_prompt: str) -> dict:

    log.info("Pass: gap_check")
    start, end = PASS_PAGE_RANGES["gap_check"]

    log.info(f"  Extracting full PDF ({end - start + 1} pages)…")
    pdf_text = extract_pdf_pages(pdf_path, start, end)
    dataset_str = json.dumps(dataset, indent=2)
    text_hash = hashlib.sha256((pdf_text + dataset_str[:500]).encode()).hexdigest()[:12]

    cached = load_cache("gap_check", text_hash)
    if cached is not None:
        return cached

    pass_prompt = load_pass_prompt("gap_check")
    user_message = f"""
## Standard text (full document)

{pdf_text}

---

## Extracted dataset (to review)

{dataset_str}

---

## Your task

{pass_prompt}
""".strip()

    log.info(f"  Sending gap check ({len(user_message):,} chars)…")
    result = call_llm(client, system_prompt, user_message, "gap_check")
    save_cache("gap_check", text_hash, result)
    return result


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def assemble_dataset(pass_results: dict) -> dict:
    """Merge all pass outputs into the final dataset structure."""
    return {
        "$schema": "./openzrplus.schema.json",
        "meta": {
            "standard_name":     "OpenZR+ MSA Technical Specification",
            "version":           "3.0",
            "revision_date":     "2023-07-28",
            "source_url":        PDF_URL,
            "publisher":         "OpenZR+ MSA",
            "dataset_version":   "0.1.0",
            "extraction_status": "llm_extracted",
            "extracted_by":      f"extract_pipeline.py / {MODEL}",
            "verified_by":       None,
            "last_updated":      str(date.today()),
            "changelog":         [{"date": str(date.today()), "change": "Initial LLM extraction"}],
            "related_standards": [
                {"standard_id": "OIF-400ZR-01.0",  "name": "OIF 400ZR Implementation Agreement",       "relationship": "normative_reference"},
                {"standard_id": "ITU-T-G.709",      "name": "ITU-T G.709 OTN Interfaces",               "relationship": "normative_reference"},
                {"standard_id": "SFF-8024",         "name": "SFF-8024 Transceiver Management",          "relationship": "normative_reference"},
                {"standard_id": "IEEE-802.3",       "name": "IEEE 802.3 Ethernet",                       "relationship": "informative_reference"},
                {"standard_id": "CMIS-5.0",         "name": "Common Management Interface Specification", "relationship": "peer_standard"},
                {"standard_id": "OIF-C-CMIS",       "name": "OIF Coherent CMIS",                        "relationship": "peer_standard"},
            ],
        },
        "identity":           pass_results.get("identity",         {}).get("identity",         []),
        "line_encoding":      pass_results.get("line_encoding",    {}).get("line_encoding",    []),
        "framing":            pass_results.get("framing",          {}).get("framing",          []),
        "optical_specs": {
            "dwdm_link":     pass_results.get("dwdm_link",         {}).get("dwdm_link",        []),
            "tx_optical":    pass_results.get("tx_optical",        {}).get("tx_optical",       []),
            "rx_optical":    pass_results.get("rx_optical",        {}).get("rx_optical",       []),
            "mask_profiles": pass_results.get("mask_profiles",     {}).get("mask_profiles",    []),
        },
        "client_interfaces":  [],   # §12 is informative; populate manually or add a pass
        "compliance_rules":   pass_results.get("compliance_rules", {}).get("compliance_rules", []),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_dataset(dataset: dict) -> list[str]:
    """Run JSON Schema validation. Returns list of error strings."""
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(dataset), key=lambda e: e.path)
    return [f"{' > '.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors]


def validate_extraction_quality(dataset: dict) -> list[str]:
    """
    Business-logic quality checks beyond JSON Schema.
    Returns list of warning strings.
    """
    warnings = []

    # 1. All identity entries should have at least one host interface
    for entry in dataset.get("identity", []):
        mid = entry.get("media_interface_id", "?")
        if not entry.get("supported_host_interfaces"):
            warnings.append(f"identity[{mid}]: missing supported_host_interfaces")

    # 2. All optical params should have applies_to set
    for section in ["dwdm_link", "tx_optical", "rx_optical"]:
        for param in dataset.get("optical_specs", {}).get(section, []):
            pid = param.get("id", "?")
            if not param.get("applies_to"):
                warnings.append(f"optical_specs.{section}[{pid}]: applies_to is empty")
            if param.get("extraction_confidence") == "low":
                warnings.append(f"optical_specs.{section}[{pid}]: LOW confidence — needs human review")
            if param.get("min") is None and param.get("max") is None:
                warnings.append(f"optical_specs.{section}[{pid}]: both min and max are null")

    # 3. Mask profiles should have at least 3 points
    for mask in dataset.get("optical_specs", {}).get("mask_profiles", []):
        mid = mask.get("mask_id", "?")
        if len(mask.get("points", [])) < 3:
            warnings.append(f"mask_profiles[{mid}]: only {len(mask.get('points', []))} points — likely incomplete")

    # 4. Compliance rules should cover all optical param ids
    rule_refs = {r.get("parameter_ref") for r in dataset.get("compliance_rules", [])}
    for section in ["tx_optical", "rx_optical", "dwdm_link"]:
        for param in dataset.get("optical_specs", {}).get(section, []):
            pid = param.get("id")
            if pid and pid not in rule_refs and param.get("severity") == "mandatory":
                warnings.append(f"compliance_rules: no rule references mandatory param '{pid}'")

    # 5. Check identity count — spec defines ~14 media interface IDs
    n = len(dataset.get("identity", []))
    if n < 10:
        warnings.append(f"identity: only {n} entries — expected ~14. Extraction may be incomplete.")

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OpenZR+ extraction pipeline")
    parser.add_argument("--pdf",       default="openzrplus_rev3p0_final2.pdf", help="Path to the OpenZR+ PDF")
    parser.add_argument("--passes",    nargs="+", help="Run only specific passes (default: all)")
    parser.add_argument("--no-cache",  action="store_true", help="Ignore cache, re-run all passes")
    parser.add_argument("--skip-gap",  action="store_true", help="Skip the gap-check pass")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        log.error(f"PDF not found: {pdf_path}")
        log.info(f"Download from: {PDF_URL}")
        raise SystemExit(1)

    if not SCHEMA_PATH.exists():
        log.error(f"Schema not found: {SCHEMA_PATH}")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    if args.no_cache and CACHE_DIR.exists():
        import shutil
        shutil.rmtree(CACHE_DIR)
        log.info("Cache cleared.")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set")

    client        = anthropic.Anthropic(api_key=api_key)
    system_prompt = load_system_prompt()

    ordered_passes = ["identity", "line_encoding", "framing",
                      "dwdm_link", "tx_optical", "rx_optical",
                      "mask_profiles", "compliance_rules"]

    if args.passes:
        ordered_passes = [p for p in ordered_passes if p in args.passes]

    # ── Run extraction passes ──
    pass_results = {}
    for pass_name in ordered_passes:
        result = run_pass(client, pass_name, pdf_path, system_prompt)
        pass_results[pass_name] = result

    # ── Assemble ──
    log.info("Assembling dataset…")
    dataset = assemble_dataset(pass_results)

    # ── Gap check ──
    if not args.skip_gap:
        log.info("Running gap check pass…")
        gap_report = run_gap_check(client, pdf_path, dataset, system_prompt)
        gap_path = OUTPUT_DIR / "gap_report.json"
        gap_path.write_text(json.dumps(gap_report, indent=2))
        log.info(f"Gap report → {gap_path}")

        # Surface critical gaps
        for issue_type in ["wrong_values", "dropped_conditions", "dropped_footnotes"]:
            issues = gap_report.get(issue_type, [])
            if issues:
                log.warning(f"  {len(issues)} {issue_type} found — review gap_report.json")

    # ── JSON Schema validation ──
    log.info("Validating against JSON Schema…")
    schema_errors = validate_dataset(dataset)
    if schema_errors:
        log.error(f"  {len(schema_errors)} schema errors:")
        for e in schema_errors[:10]:
            log.error(f"    {e}")
    else:
        log.info("  Schema validation: PASSED")

    # ── Quality checks ──
    log.info("Running quality checks…")
    quality_warnings = validate_extraction_quality(dataset)
    if quality_warnings:
        log.warning(f"  {len(quality_warnings)} quality warnings:")
        for w in quality_warnings[:15]:
            log.warning(f"    {w}")
    else:
        log.info("  Quality checks: PASSED")

    # ── Write output ──
    out_path = OUTPUT_DIR / "openzrplus_dataset.json"
    out_path.write_text(json.dumps(dataset, indent=2))
    log.info(f"\nDataset → {out_path}")

    # ── Summary ──
    id_count    = len(dataset.get("identity", []))
    opt_tx      = len(dataset.get("optical_specs", {}).get("tx_optical", []))
    opt_rx      = len(dataset.get("optical_specs", {}).get("rx_optical", []))
    rules       = len(dataset.get("compliance_rules", []))
    masks       = len(dataset.get("optical_specs", {}).get("mask_profiles", []))
    log.info(f"\nSummary:")
    log.info(f"  identity entries:       {id_count}")
    log.info(f"  tx_optical params:      {opt_tx}")
    log.info(f"  rx_optical params:      {opt_rx}")
    log.info(f"  mask profiles:          {masks}")
    log.info(f"  compliance rules:       {rules}")
    log.info(f"  schema errors:          {len(schema_errors)}")
    log.info(f"  quality warnings:       {len(quality_warnings)}")

    if schema_errors or quality_warnings:
        log.warning("\nReview errors/warnings before setting extraction_status to 'frozen'.")
    else:
        log.info("\nAll checks passed. Update meta.extraction_status to 'human_verified' after review.")


if __name__ == "__main__":
    main()
