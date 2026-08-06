#!/usr/bin/env python3
"""Write an experiment outcome against an approved spend receipt.

This records results only; it cannot approve or execute spending.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("experiment_id"); p.add_argument("spend_receipt_id"); p.add_argument("hypothesis"); p.add_argument("result"); p.add_argument("--metric",action="append",default=[]); p.add_argument("--falsifier",required=True); p.add_argument("--out",type=Path,default=Path("reports")); a=p.parse_args()
    if len(a.spend_receipt_id)!=64 or any(c not in '0123456789abcdef' for c in a.spend_receipt_id): raise SystemExit('spend_receipt_id must be a receipt sha256')
    body={"report_type":"experiment_outcome","experiment_id":a.experiment_id,"spend_receipt_id":a.spend_receipt_id,"hypothesis":a.hypothesis,"result":a.result,"metrics":a.metric,"falsifier":a.falsifier,"reported_at":datetime.now(timezone.utc).isoformat()}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest(); body["report_id"]=digest
    path=a.out/(a.experiment_id+"-"+digest[:16]+".json"); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(body,indent=2)+"\n"); print(json.dumps({"report_id":digest,"path":str(path)}))
if __name__ == '__main__': main()
