# Runbook Template

> Standard format for all runbooks in this directory.

---

```markdown
# Runbook: [Title]

## Severity: [P1-Critical / P2-High / P3-Medium / P4-Low]

## Symptoms
- What the operator/agent observes
- Log patterns, missing notifications, unexpected behavior

## Diagnostic Steps
1. Check X → if Y → go to step N
2. Check Z → ...

## Resolution
- Step-by-step fix procedure
- Commands to run
- Config changes to make

## Prevention
- How to avoid this in the future
- Monitoring improvements
- Config recommendations

## Escalation
- When to escalate beyond automated fixes
- Who/what to contact
```
