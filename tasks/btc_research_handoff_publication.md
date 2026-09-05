# Research handoff publication review — 2026-09-05

The user requested a findings file that another AI agent can use on another
device, and publication to the existing GitHub repository. The entry point is
[RESEARCH_PIPELINE_HANDOFF.md](../RESEARCH_PIPELINE_HANDOFF.md). The dedicated
branch is `codex/research-pipeline-handoff-20260905`, based on `447ad20`.

The publication includes the previously completed adaptive implementation,
benchmark, tests, documentation and compact research evidence. The raw inputs
were already tracked; generated large CSVs, authentication files and temporary
tooling are excluded. The initial reviewed stage contained 152 files and about
2.81 MB of content; this review note is an additional small document.

## Verified before publication

- Fresh focused run: **293 pipeline tests passed in 71.16 seconds**.
- Markdown link verification passed after removing the owned pytest output.
- All **30 fingerprinted code blobs** in the Git index match the frozen protocol.
- All **88 new research evidence files** in the index match their local bytes.
- Seven small SQLite research archives were also expanded read-only for scanning.
- No staged file exceeded the repository's 500 KiB added-file threshold.
- Three pre-existing checker modules preserved through `.gitattributes` differ
  only in line-ending storage; ignoring end-of-line whitespace yields no semantic
  diff. No raw market CSV content change is staged.
- All earlier benchmark source, data and artifact identity checks remain valid.

`.gitattributes` preserves exact bytes for fingerprinted code and dated evidence,
including CRLF where present. Its whitespace settings recognize CRLF while
retaining trailing-space, blank-EOF and space-before-tab checks. It does not
normalize or rewrite frozen artifacts.

## Secret-scanner review and remaining checks

A temporary copy of the repository's `detect-secrets==1.5.0` tool scanned staged
files and expanded SQLite records. It reported 504 candidates: 463 hex-entropy
fingerprints in research hash/path fields, 40 canonical packet-path strings,
and one explicit fake-password literal in a credential-redaction regression.
A read-only field/value-shape review classified each candidate. No unreviewed
credential finding remained, and detected values were not printed by the scan.

The automatic approval reviewer rejected a proposed update to
`.secrets.baseline`, stating that persistent security-control exceptions require
explicit user authorization. That action was not performed. The subsequent
review script removed its baseline-writing code; the baseline remains unchanged.
Thus the raw repository secret scan can continue to flag these reviewed values.
This review is not a claim that the unmodified detector or all CI checks pass.

Architecture lint still has the pre-existing 865-line Phase 1 module violation.
`git diff --check` reports retained extra blank EOF lines in four fingerprinted
pipeline files. Preserving their exact code identity takes precedence over
silently reformatting an already frozen historical record for this handoff.
The handoff lists these limitations for the next agent.

No model calls, trading operations, purchases, force push or merge into the
main branch are part of publication. The final user response records the pushed
commit and remote verification, avoiding a self-referential commit hash here.
