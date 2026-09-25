# Traffic flip is the only promote/rollback mechanism

Promotion and rollback both mean `POST /admin/route {target}` on the Proxy, not redeploy or image retag. This keeps Execution real but trivially reversible for the demo.

## Consequences

Decision and Proposal logic must not assume deploy powers; risk scoring assumes flip cost is near-zero and fully reversible.
