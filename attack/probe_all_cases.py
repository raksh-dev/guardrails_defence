"""
Probe ALL evaluator cases directly against the guardrail pattern scanner
(no HTTP round-trip needed — just imports the pattern module).
Prints which attacks slip through InputGuard and DocumentGuard.
"""
import sys, os, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFENCE_ROOT = PROJECT_ROOT / "defence"
DATA_DIR = Path(__file__).resolve().parent / "data"

os.environ.update({
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
    "STORAGE_URL": "https://x.storage.supabase.co",
    "STORAGE_ACCOUNT_SECRET": "x",
    "STORAGE_BUCKET_NAME": "books",
    "LLM_API_KEY": "sk-test",
    "LLM_PROVIDER": "openrouter",
    "LLM_MODEL": "test",
    "GUARDRAILS_ENABLED": "true",
})

sys.path.insert(0, str(DEFENCE_ROOT))

import warnings
warnings.filterwarnings("ignore")

from services.guardrails.patterns import scan_input, scan_document

with open(DATA_DIR / "adversarial_prompts.json", encoding="utf-8") as f:
    adv = json.load(f)

with open(DATA_DIR / "pdf_adversarial_prompts.json", encoding="utf-8") as f:
    pdf = json.load(f)

all_cases = adv + pdf

blocked_count = 0
slip_count = 0
benign_fp = 0   # benign cases that get blocked (false positives)
benign_ok = 0   # benign cases that pass (true negatives)

print()
print("=" * 80)
print("FULL GUARDRAIL PROBE — All 63 evaluator cases vs. defence patterns")
print("=" * 80)
print(f"{'ID':<12} {'Severity':<10} {'Category':<30} {'Result'}")
print("-" * 80)

for c in all_cases:
    cid      = c.get("id", "?")
    cat      = c.get("category", "?")
    severity = c.get("severity", "?")
    prompt   = c.get("user_prompt", "") or ""
    doc      = c.get("external_content", "") or ""
    is_benign = cat == "benign"

    input_hit = scan_input(prompt)
    doc_hit   = scan_document(doc) if doc else None
    blocked   = bool(input_hit or doc_hit)

    if is_benign:
        if blocked:
            result = "FALSE POSITIVE  (benign blocked)"
            benign_fp += 1
        else:
            result = "TRUE NEGATIVE   (benign allowed)"
            benign_ok += 1
    else:
        if blocked:
            result = "BLOCKED         (guardrail fires)"
            blocked_count += 1
        else:
            result = "<<< SLIPS THROUGH (security gap) <<<"
            slip_count += 1

    print(f"{cid:<12} {severity:<10} {cat[:28]:<30} {result}")

total_attacks = len(all_cases) - (benign_fp + benign_ok)
print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total cases         : {len(all_cases)}")
print(f"Benign (true neg)   : {benign_ok}  correctly allowed through")
print(f"Benign (false pos)  : {benign_fp}  blocked (false alarm)")
print(f"Attacks blocked     : {blocked_count} / {total_attacks}")
print(f"Attacks slip through: {slip_count} / {total_attacks}  <-- SECURITY GAPS")
print("=" * 80)
