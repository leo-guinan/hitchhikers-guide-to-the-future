# Mincoin marketplace boundary

## v0 scope

The marketplace is a public directory for bounded Mincoin projects. It currently supports:

- a card linking to the live Mincoin page;
- project cards with visible promise, status, and evidence boundary;
- local participation intents with `funds_moved: false` and `financial_claim_issued: false`;
- local work receipts containing `promise`, `result`, evidence pointers, and an `energy_state`;
- a distinction between recorded prepaid energy and cash owed.

The first page is at `/market/` on the HGF site.

## Economic boundary

A work receipt is evidence of action and a claim for review. It is not, by itself, a contract, wage, debt, equity interest, token, investment, return, or payment obligation. `requested_future_pay_usd` is a requested valuation for review, not a booked liability.

An accepted-energy ledger, if added later, must keep at least these states separate:

```text
submitted -> evidence_review -> accepted_energy -> payable_under_terms -> settled | rejected | disputed
```

Only a separate agreement can move an accepted receipt into `payable_under_terms`. Settlement requires its own receipt with amount, currency/asset, recipient, evidence, timestamp, and outcome. Corrections are append-only.

## Investment boundary

The marketplace does not currently accept investments, pool funds, issue units or tokens, connect wallets, custody assets, promise returns, allocate ownership, or redeem positions. A claim whose value or payout depends on another project's growth or work may be a security or another regulated product. Any operative rail requires reviewed legal structure, jurisdiction and eligibility rules, disclosures, custody/transfer design, tax treatment, and a settlement oracle before money moves.

The participation form is therefore an intent/modeling surface only. It stores a local receipt and explicitly records `funds_moved: false` and `financial_claim_issued: false`.

## Work accounting principle

The system can show that someone acted before money arrived without claiming that trust was unnecessary. The receipt is the trust substrate: promise before action, result after action, evidence for inspection, and visible mismatch when the work is incomplete or rejected. “Prepaid energy” measures accepted work in the system; it does not erase counterparty, acceptance, liquidity, or legal risk.
