# GuardRail

Canary deployment verifier with governance-gated remediation for developer release workflows.

## Language

**Stable**:
The current production version serving live traffic by default.
_Avoid_: prod, master

**Canary**:
The new version running side-by-side with Stable carrying real planted bugs for verification.
_Avoid_: beta, preview

**Proxy**:
The routing layer that sends live traffic to Stable or Canary and exposes the traffic flip.
_Avoid_: gateway, router

**Traffic flip**:
The sole promotion mechanism: switching Proxy target between Stable and Canary.
_Avoid_: promote, rollback, redeploy

**Traffic-runner**:
The synthetic verifier that fires identical spec-derived requests at Stable and Canary directly.
_Avoid_: load tester, simulator

**Verification**:
Side-by-side comparison of status, latency, and response diffs from Traffic-runner.
_Avoid_: monitoring, testing

**Criticality map**:
Doc-ingest output ranking which endpoints changed and how severe a break is.
_Avoid_: changelog, spec summary

**Decision**:
The verdict from aggregated metrics plus Criticality map: escalate or keep canary.
_Avoid_: judgment, analysis

**Proposal**:
A ranked remediation action with risk score, blast radius, and reversibility.
_Avoid_: suggestion, fix

**Approval checkpoint**:
The human gate in the dashboard that must approve a Proposal before Execution.
_Avoid_: confirmation, sign-off

**Execution**:
Running the approved traffic flip via the Proxy admin endpoint.
_Avoid_: action, run

**Audit trail**:
The append-only record of every Proposal, Decision, approver, and outcome.
_Avoid_: log, history
