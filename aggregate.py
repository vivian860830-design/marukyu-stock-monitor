"""Runs once per workflow, in the `aggregate` job, after all 12 `capture`
matrix jobs have finished (see monitor.yml). Downloads their per-product
JSON artifacts, compares each SKU against stock_state.json, and only for
a true SOLD_OUT -> AVAILABLE transition, adds it to the GAS webhook
payload. Then writes the updated stock_state.json for the workflow to
commit back to the repository.

State rules (unchanged from the single-job v4 monitor.py this replaces):
  - A row with status UNKNOWN never overwrites stock_state.json and never
    counts as a transition — a Cloudflare hiccup on one product must not
    corrupt its baseline or fire a false alert.
  - A SKU seen for the first time is recorded as baseline only; no
    notification on first sight.
  - Only SOLD_OUT -> AVAILABLE counts as a restock.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", "product-results"))
STATE_PATH = Path("stock_state.json")
EVIDENCE_DIR = Path("diagnostic-output")


def load_state():
    if not STATE_PATH.exists():
        return {"updated_at": None, "skus": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        print("WARNING: stock_state.json exists but could not be parsed; starting a fresh baseline.")
        return {"updated_at": None, "skus": {}}
    if not isinstance(data, dict) or not isinstance(data.get("skus"), dict):
        print("WARNING: stock_state.json exists but is missing/malformed 'skus'; starting a fresh baseline "
              "(existing unrelated keys, if any, are dropped).")
        return {"updated_at": None, "skus": {}}
    return data


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_product_results():
    """Each capture_one.py run uploaded diagnostic-output/<slug>.json as
    its own artifact; the workflow downloads all of them, merged, into
    RESULTS_DIR before this script runs. A missing/failed matrix job
    simply won't have a file here — that product is skipped this round,
    not treated as SOLD_OUT or anything else."""
    results = []
    if not RESULTS_DIR.exists():
        print(f"WARNING: {RESULTS_DIR} does not exist; no product results to aggregate.")
        return results
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as error:
            print(f"WARNING: could not parse {path}: {type(error).__name__}")
    return results


def diff_and_update(state, result):
    zh, en, url = result.get("product_zh", ""), result.get("product_en", ""), result.get("product_url", "")
    restocked = []
    for row in result.get("rows", []):
        key = row.get("variation_id")
        if not key:
            continue
        current = row["status"]
        if current == "UNKNOWN":
            continue
        previous = state["skus"].get(key)
        if previous is not None and previous.get("status") == "SOLD_OUT" and current == "AVAILABLE":
            restocked.append({"sku": row["sku"], "size": row["size"]})
        state["skus"][key] = {
            "product_zh": zh, "product_en": en,
            "sku": row["sku"], "size": row["size"],
            "status": current,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    return {"zh": zh, "en": en, "url": url, "variants": restocked} if restocked else None


def send_gas_notification(products_with_restocks, taiwan, dry_run):
    EVIDENCE_DIR.mkdir(exist_ok=True)
    webhook_url = os.environ.get("GAS_WEBHOOK_URL", "")
    secret = os.environ.get("MONITOR_SECRET", "")
    payload = {"source": "github-monitor", "secret": secret, "products": products_with_restocks, "taiwan": taiwan}
    (EVIDENCE_DIR / "gas-notification-payload.json").write_text(
        json.dumps({**payload, "secret": "***redacted***"}, ensure_ascii=False, indent=2), encoding="utf-8")

    if dry_run:
        print("DRY_RUN=true: not sending. Payload would have been:")
        print(json.dumps({**payload, "secret": "***redacted***"}, ensure_ascii=False, indent=2))
        return
    if not webhook_url or not secret:
        print("ERROR: GAS_WEBHOOK_URL or MONITOR_SECRET is not set; cannot send notification.")
        return

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"GAS webhook responded: HTTP {response.status}")
    except urllib.error.HTTPError as error:
        print(f"GAS webhook HTTP error: {error.code} {error.reason}")
    except urllib.error.URLError as error:
        print(f"GAS webhook request failed: {error.reason}")


def main():
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
    state = load_state()
    results = load_product_results()

    print(f"Loaded {len(results)} product result(s) out of 12 expected.")
    restocks = []
    taiwan = "UNKNOWN"
    for result in results:
        slug = result.get("product_slug", "?")
        print(f"{slug}: page_status={result.get('page_status')} page_reason={result.get('page_reason')}")
        if taiwan == "UNKNOWN":
            taiwan = result.get("taiwan", "UNKNOWN")
        restock = diff_and_update(state, result)
        if restock:
            restocks.append(restock)

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    print(f"taiwan shipping signal: {taiwan}")
    print(f"DRY_RUN: {dry_run}")
    if restocks:
        print(f"RESTOCK DETECTED: {len(restocks)} product(s) -> {[r['en'] for r in restocks]}")
        send_gas_notification(restocks, taiwan, dry_run)
    else:
        print("No SOLD_OUT -> AVAILABLE transitions this run. No notification sent.")


if __name__ == "__main__":
    main()
