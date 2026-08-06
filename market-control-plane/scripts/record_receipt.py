#!/usr/bin/env python3
"""Create a public-safe revenue receipt from an independently observed chain event.

This script never connects to a wallet, signs, broadcasts, or moves funds.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

CHAINS = {"base", "ethereum", "solana", "polygon", "quai"}
TYPES = {"deposit", "revenue_transfer", "experiment_spend"}
STATUSES = {"observed", "confirmed", "proposed", "executed", "rejected", "superseded"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("receipt_type", choices=sorted(TYPES))
    p.add_argument("chain", choices=sorted(CHAINS))
    p.add_argument("tx_hash")
    p.add_argument("amount")
    p.add_argument("asset")
    p.add_argument("--wallet-address")
    p.add_argument("--treasury-address")
    p.add_argument("--confirmations", type=int)
    p.add_argument("--status", choices=sorted(STATUSES), default="observed")
    p.add_argument("--proposal-id")
    p.add_argument("--out", type=Path, default=Path("receipts"))
    args=p.parse_args()
    if not args.tx_hash.strip() or not args.asset.strip(): raise SystemExit("tx_hash and asset are required")
    if not args.amount.replace(".","",1).isdigit() or float(args.amount) < 0: raise SystemExit("amount must be a non-negative decimal string")
    if args.confirmations is not None and args.confirmations < 0: raise SystemExit("confirmations cannot be negative")
    body={"receipt_type":args.receipt_type,"mode":"dry_run","chain":args.chain,"tx_hash":args.tx_hash,"amount":args.amount,"asset":args.asset,"wallet_address":args.wallet_address,"treasury_address":args.treasury_address,"observed_at":datetime.now(timezone.utc).isoformat(),"confirmations":args.confirmations,"status":args.status,"proposal_id":args.proposal_id,"github_receipt_url":None}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest(); body["receipt_id"]=digest
    path=args.out/args.receipt_type/args.chain/(digest+".json"); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(body,indent=2)+"\n")
    print(json.dumps({"receipt_id":digest,"path":str(path),"mode":"dry_run","funds_moved":False}))
if __name__ == "__main__": main()
