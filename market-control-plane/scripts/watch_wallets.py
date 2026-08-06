#!/usr/bin/env python3
"""Watch public receiving wallets and emit bounded Marvin activity alerts.

This is observation-only. It never signs, sweeps, converts, or assigns entitlement.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(os.environ.get("WALLET_MONITOR_STATE", "/var/lib/hgf-wallet-monitor/state.json"))
MAX_BLOCKS = 20
MAX_ALERTS_PER_RUN = 3
MAX_ALERTS_PER_DAY = 10
EVM = {
    "Ethereum": ("https://ethereum.publicnode.com", "0x0be197c794575579f2f238a68edf2fc5f92817ac"),
    "Base": ("https://mainnet.base.org", "0x0be197c794575579f2f238a68edf2fc5f92817ac"),
    "Polygon": ("https://polygon.drpc.org", "0x0be197c794575579f2f238a68edf2fc5f92817ac"),
    "Quai": ("https://rpc.quai.network/cyprus1", "0x005A3560C44e506626A26352466429cC963F9fB7"),
}
SOLANA = ("https://api.mainnet-beta.solana.com", "FFAdvcr2CUPbaQSypK3c8WfQo3SuyBh5YKrtzZRSvg34")  # git-secret-ignore public Solana receiving address, not a secret


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "HGF-Wallet-Observer/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.loads(response.read())
            if "error" in result:
                raise RuntimeError(f"{method}: provider error {result['error'].get('code')}")
            return result.get("result")
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 429) or attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{method}: provider retry exhausted")


def post_alert(chain, alert_number):
    text = (f"Network activity detected on {chain} (alert {alert_number}/{MAX_ALERTS_PER_DAY}). "
            "The receiving wallet has new public activity requiring human review. "
            "Marvin did not sign, sweep, or convert anything.")
    result = subprocess.run(["xurl", "--app", "marvin-x", "post", text], capture_output=True, text=True, timeout=45)
    if result.returncode != 0:
        raise RuntimeError(f"xurl post failed for {chain}: exit {result.returncode}")
    match = re.search(r'"id"\s*:\s*"(\d+)"', result.stdout)
    tweet_id = match.group(1) if match else None
    if not tweet_id:
        raise RuntimeError(f"xurl post returned no tweet id for {chain}")
    readback = subprocess.run(["xurl", "--app", "marvin-x", "read", tweet_id], capture_output=True, text=True, timeout=45)
    if readback.returncode != 0 or text not in readback.stdout:
        raise RuntimeError(f"xurl readback failed for {chain} tweet {tweet_id}")
    return tweet_id


def load_state():
    if not STATE_PATH.exists():
        return {"version": 1, "initialized": False, "chains": {}, "events": {}}
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE_PATH)


def evm_events(chain, url, address, state):
    latest = int(rpc(url, "eth_blockNumber", []), 16)
    previous = state["chains"].get(chain, {}).get("last_block")
    if previous is None:
        state["chains"][chain] = {"last_block": latest}
        return [], "baseline"
    start = max(previous + 1, latest - MAX_BLOCKS + 1)
    found = []
    for number in range(start, latest + 1):
        block = rpc(url, "eth_getBlockByNumber", [hex(number), True]) or {}
        for tx in block.get("transactions", []):
            if (tx.get("to") or "").lower() == address.lower():
                found.append(tx.get("hash"))
    state["chains"][chain] = {"last_block": latest}
    return [x for x in found if x], "scan"


def solana_events(state):
    url, address = SOLANA
    before = state["chains"].get("Solana", {}).get("before")
    params = [address, {"limit": 100}]
    if before:
        params[1]["before"] = before
    rows = rpc(url, "getSignaturesForAddress", params) or []
    if not rows:
        return [], "baseline" if not before else "scan"
    state["chains"]["Solana"] = {"before": rows[0].get("signature")}
    return [r.get("signature") for r in reversed(rows) if r.get("signature")], "scan"


def main():
    state = load_state()
    new = []
    provider_errors = []
    modes = {}
    for chain, (url, address) in EVM.items():
        try:
            events, mode = evm_events(chain, url, address, state)
            modes[chain] = mode
            new.extend((chain, event) for event in events)
        except Exception as exc:
            provider_errors.append({"chain": chain, "error": str(exc)})
            print(json.dumps({"status": "provider_error", "chain": chain, "error": str(exc)}))
    try:
        events, mode = solana_events(state)
        modes["Solana"] = mode
        new.extend(("Solana", event) for event in events)
    except Exception as exc:
        provider_errors.append({"chain": "Solana", "error": str(exc)})
        print(json.dumps({"status": "provider_error", "chain": "Solana", "error": str(exc)}))

    if provider_errors:
        state["last_provider_errors"] = provider_errors
        save_state(state)
        print(json.dumps({"status": "provider_degraded", "errors": provider_errors}))
        return 1

    if not state.get("initialized"):
        state["initialized"] = True
        state.pop("last_provider_errors", None)
        save_state(state)
        print(json.dumps({"status": "baseline", "chains": modes}))
        return 0

    alerts = []
    today = datetime.now(timezone.utc).date().isoformat()
    budget = state.get("alert_budget", {})
    if budget.get("date") != today:
        budget = {"date": today, "count": 0}
    for chain, event_id in new:
        key = f"{chain}:{event_id}"
        if key in state["events"]:
            continue
        if len(alerts) >= MAX_ALERTS_PER_RUN or budget["count"] >= MAX_ALERTS_PER_DAY:
            state["events"][key] = {"chain": chain, "event_id": event_id, "status": "alert_suppressed_by_cap", "observed_at": int(time.time())}
            continue
        try:
            tweet_id = post_alert(chain, budget["count"] + 1)
            state["events"][key] = {"chain": chain, "event_id": event_id, "tweet_id": tweet_id, "observed_at": int(time.time())}
            budget["count"] += 1
            alerts.append({"chain": chain, "event_id": event_id, "tweet_id": tweet_id, "status": "verified_write_id"})
            save_state(state)
        except Exception as exc:
            print(json.dumps({"status": "alert_error", "chain": chain, "event_id": event_id, "error": str(exc)}))
            save_state(state)
            return 1
    state["alert_budget"] = budget
    state.pop("last_provider_errors", None)
    save_state(state)
    print(json.dumps({"status": "ok", "modes": modes, "new_events": len(new), "alerts": alerts, "daily_alerts": budget["count"], "caps": {"per_run": MAX_ALERTS_PER_RUN, "per_day": MAX_ALERTS_PER_DAY}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
