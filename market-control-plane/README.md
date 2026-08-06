# Revenue control plane

This directory defines the accounting and evidence boundary for the Proximity Market.

It is deliberately fail-closed:

- no private keys or seed phrases are accepted by the repository;
- no transaction signer is implemented here;
- chain state is authoritative for deposits and transfers;
- GitHub receipts are a public audit mirror, not a balance ledger;
- every transfer into `revenue` is a proposal requiring an external multisig/signing policy;
- every experiment spend must point to a proposal and later receive an outcome report.

## Chain slots

The initial market UI exposes Base, Ethereum, Solana, Polygon, and Quai. Quai is represented as its own adapter slot for Cyprus-1 (mainnet chain ID 9, `https://rpc.quai.network/cyprus1`). Quai uses shard-scoped Quai/Qi address rules; an ordinary EVM address validator is not sufficient. Replace the placeholder addresses only through a private deployment configuration after custody review. Never commit private keys.

## Lifecycle

```text
deposit observed
  -> confirmation threshold reached
  -> deposit receipt
  -> revenue transfer proposal
  -> multisig/manual approval outside this repo
  -> chain transaction read-back
  -> public GitHub receipt
  -> experiment spend proposal
  -> spend transaction read-back
  -> outcome report
```

A GitHub commit or issue is not proof that funds moved. It is only the public publication of a receipt whose transaction hash must be independently read back from the chain.

## Revenue and experiment accounting

The control plane separates:

- `deposit`: funds arriving at a chain wallet;
- `revenue_transfer`: movement from a chain wallet into the central revenue treasury;
- `experiment_spend`: an approved use of revenue resources;
- `experiment_outcome`: the measured result, including the falsifier and whether the hypothesis survived.

The current market is a non-custodial prototype. Until a reviewed legal and custody implementation exists, these records may be produced in dry-run mode only.
