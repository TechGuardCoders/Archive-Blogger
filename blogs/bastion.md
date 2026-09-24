# Bastion: The Security Shell That Wraps Our Model Gateway

Every model endpoint at Tech Guard used to run on trust. A valid looking API key came in, the gateway forwarded the request, and the system assumed the key meant what it claimed. That assumption does not survive contact with a real adversary. Bastion is the security shell we built to close that gap. It sits between every client and the gateway, issuing hashed, versioned API keys with fine grained scopes, recording a tamper evident audit chain of every action, and sandboxing any tool execution behind hard timeouts.

We did not ship it on faith. We built an eleven point attack drill that threw forged keys, tampered audit logs, privilege escalation attempts, and runaway sandbox code at Bastion. Every attack was rejected or contained, and the drill surfaced a real privilege escalation bug in the rotation flow before production ever could. This post explains how each layer works, why it is built that way, and what the drill proved.

## Hashed, Versioned Keys With Fine Grained Scopes

Bastion never stores a raw API key. When a key is issued, the plaintext is shown once to the caller, and only a salted hash lands in the database. A database dump reveals nothing reusable. Verification hashes the presented key with the same salted scheme and compares, so the server holds no secret worth stealing in the first place.

Every key carries a version number. When a key rotates, the old version is marked retired with an expiry window rather than deleted immediately, which lets long running jobs finish while new traffic uses the new key. The version also gives the audit chain a stable identity to reference, so a log entry says exactly which key generation performed an action.

Scopes are the part that does the real work. A key does not grant "access to the API"; it grants named capabilities like `models:invoke`, `models:list`, or `tools:run`, each bound to specific resources. A data pipeline key that only needs inference cannot touch admin routes even if its bearer goes rogue. Scope checks happen before the gateway sees the request, so an overreaching call dies at the shell, not inside the system.

## A Tamper Evident Audit Chain

Bastion logs every meaningful event: key issuance, scope checks, denials, tool executions, timeouts, rotations. But a log an attacker can edit is not evidence, it is fiction. Each audit record includes a hash of the previous record, forming a chain where any modification breaks every hash after it.

The design is deliberately simple. Each record is serialized, hashed, and the hash is embedded in the next record. Verifying the chain means replaying the hashes from the genesis entry. If an attacker edits record 4,182 to hide a denial, the recomputed hash no longer matches the value stored in record 4,183, and the break is visible immediately. Periodic chain heads can also be exported off host, so an attacker with host access still cannot rewrite history without the exported anchor contradicting them.

This matters for incidents, not just compliance. When the attack drill tampered with audit records, Bastion flagged the break in the chain on the next verification pass. In a real breach, that is the difference between reconstructing what happened and guessing.

## Sandboxed Tool Execution With Hard Timeouts

Model endpoints increasingly execute tools: code, retrievers, external API calls. That is the highest risk surface in the whole stack, because the input is model generated and therefore not fully trusted. Bastion sandboxes every tool execution in an isolated environment with no network access unless explicitly granted, a restricted filesystem view, and resource ceilings.

Hard timeouts are non negotiable. A tool gets a wall clock budget, and when it expires, Bastion kills the process group, releases the sandbox, and records the timeout in the audit chain. There is no soft cancellation that runaway code can ignore. CPU and memory limits back the timeout so a busy loop cannot win by burning cycles faster than the clock reads.

The drill threw deliberately runaway payloads at this layer: infinite loops, memory bombs, and code that tried to escape the working directory. Each one was contained. The execution died, the sandbox was torn down, and the only trace was a timeout entry in the audit log. Containment, not prevention, is the right goal here. Assume the code is hostile and make hostile code boring.

## The Eleven Point Attack Drill

We wrote the drill as eleven adversarial scenarios run against a production identical deployment. The list covered the attack classes that actually matter for a gateway shell:

- Forged API keys: invalid signatures, replayed plaintext, and keys with invented scopes
- Tampered audit logs: edited records, deleted records, and reordered chains
- Privilege escalation: retired keys attempting live calls and scope inflation attempts
- Sandbox escape: runaway code, resource exhaustion, and filesystem probing

Each scenario asserted a specific expected outcome, so the drill fails loudly rather than "mostly passing". This is the same discipline we apply to functional tests, pointed at an adversary instead of a user.

Nine of the eleven attacks were rejected on first contact. Two exposed weaknesses, and one of those was a genuine bug rather than a tuning issue. That ratio is the normal, healthy result of red teaming your own infrastructure. A drill that passes everything on the first run usually means the drill is not trying hard enough.

## The Bug the Drill Caught in the Rotation Flow

The real find was a privilege escalation in key rotation. During a rotation, there is a window where the new key version is active and the old version is in its grace period. The rotation handler validated the new key's scopes correctly, but an old key presented during that window could inherit the scope set of the new version before its own retirement record was finalized. A retired key with narrow scopes could briefly act with broader ones.

It is a classic window bug: two state transitions, a check that read the wrong side of the boundary. In production it would have been nearly invisible, because nothing malicious was hammering rotations at the exact millisecond the state flipped. The drill hit the window on purpose, because attacking a boundary is what an adversary does.

The fix tightened the ordering: the old key's scopes are frozen and enforced for its entire grace period, and the new scope set activates only after the retirement record is committed to the audit chain. We then added the exact drill scenario as a permanent regression test. The lesson generalizes: security bugs hide in transition windows, and only tests that race the transitions find them.

## Why Verified on Every Request Beats Trust on Sight

Trust on sight is fast until it is expensive. One leaked key, one scope inflation, one unbounded tool execution, and the cost is an incident review, customer communication, and a week of forensics. Bastion moves the verification cost to every request, where it belongs, and the overhead is a hash comparison, a scope lookup, and a chain append per call.

The layered design also means failures stay local. A forged key fails at authentication. A valid key with wrong scopes fails at authorization. A malicious payload fails at the sandbox boundary. Each layer assumes the previous one can be bypassed, which is the only honest assumption in security.

And the audit chain means every one of those failures is evidence. We can answer not just "did we block it" but "what exactly was attempted, by which key version, at what time". That turns security from a defensive posture into a measurable, testable property of the system.

## Conclusion

Bastion changed the trust model of Tech Guard's model endpoints from assumed to proven. Hashed, versioned keys with fine grained scopes shrink the blast radius of any credential leak. The tamper evident audit chain makes the log a witness instead of a target. The sandbox makes hostile code a non event. And the eleven point attack drill proved all of it, while catching a real privilege escalation bug in rotation before an attacker did.

The broader point is the drill itself. Security properties you have not attacked are claims, not features. Test your boundaries the way an adversary would, make the tests permanent, and ship knowing the shell holds because you tried to break it.

---

## Alternate Titles

- Bastion: How Tech Guard Wraps Its Model Gateway in a Security Shell
- Eleven Attacks, Zero Breaches: Proving Bastion Before Production Could
- From Trust on Sight to Verified on Every Request: Inside Bastion

## X Hooks

- We attacked our own gateway eleven times. Forged keys, tampered logs, privilege escalation, runaway code. Bastion stopped all of it, and caught a real escalation bug in our rotation flow before production did.

- Your API key says it can call inference. Who verifies that on every request? Bastion does: hashed versioned keys, fine grained scopes, a tamper evident audit chain, and a sandbox with hard timeouts.
