# Ball Knowledge: One API Surface, Zero Single Points of Failure

Every internal team that touches a model eventually hits the same wall. The notebooks call one endpoint, the automation calls another, and nobody can answer the questions that matter: who is spending what, which tenant just tripped its limit, and what happens when the box serving the model dies at two in the morning. Ball Knowledge is our answer at Tech Guard. It is an OpenAI compatible gateway that sits in front of every model backend we run, routes traffic under policy, and keeps serving when infrastructure misbehaves. This post walks through what it does, how it is built, and the live chaos drill that proved the failover actually works.

## The Problem: An Endpoint Is Not a Policy

Production AI systems do not have one endpoint. They have a policy. Which tenant gets which model, what happens when the primary dies mid request, who is over budget this month, who is hammering the API with a runaway loop. Before the gateway, every consumer of our models had to encode fragments of that policy themselves, and the answers lived in scattered config files and tribal knowledge.

The failure mode is predictable. A team hardcodes the primary backend URL. That box reboots, or a deployment stalls, and their pipeline burns its retry budget against a dead socket. Meanwhile another team quietly triples their token spend and nobody notices until the invoice lands. Resilience and cost control were bolted on per consumer, inconsistently, or not at all.

Ball Knowledge moves that policy into one layer that every consumer shares. Clients speak plain OpenAI SDK protocol, so dropping the gateway in front of VS Code, Cline, or any existing integration is a base URL change. Nothing downstream rewrites their calls. Everything upstream gets enforcement that was previously a best effort promise.

## Architecture: Small Modules Behind a Stable Contract

The gateway is a FastAPI service on port 3100. A request walks a fixed pipeline before it ever reaches a backend:

1. **Authenticate.** The tenant registry maps an API key to a tenant. Bad or missing keys get a 401 immediately, before any backend is touched.
2. **Rate limit.** A sliding window limiter enforces requests per minute per tenant. Over the limit is a 429 with no backend cost.
3. **Budget guard.** The budget ledger tracks monthly token spend per tenant. Over budget is a 402, again before a single token is generated.
4. **Route and fail over.** The backend chain holds an ordered list of backends with health tracking. Healthy primaries win; dead ones get skipped.
5. **Audit.** Every auth, rejection, serve, and failover event lands in the audit log with tenant, backend, and outcome.

State lives in memory behind clean interfaces: `TenantRegistry`, `RateLimiter`, `BudgetLedger`. That is a deliberate constraint, not a shortcut. Because each component is an interface with one implementation, swapping in Redis or Postgres later is additive work, not a redesign. The routing logic never learns where the numbers came from.

In our deployment the chain is a real vLLM backend serving GLM on a DGX Spark as primary, and an in process echo server as fallback. The fallback is intentionally boring. Its job is to prove that failover semantics work, not to simulate model quality. That separation keeps the drill honest: availability is a gateway property, and quality is a backend property.

## Cost Controls: Enforced, Not Advised

A budget nobody enforces is a spreadsheet. Ball Knowledge enforces budgets at the front door, in the same code path as authentication, so there is no window where a request bypasses accounting.

The specifics matter for engineers wiring this up:

- Limits are per tenant, not per key or per IP. A tenant with several keys still draws from one pool, which matches how teams actually consume a shared platform.
- Rejections are cheap and early. A 402 or 429 costs microseconds on the gateway. The same rejection after a backend round trip would have already spent capacity on a request that was never going to be honored.
- Every serve event records token usage against the ledger, so a tenant can approach its cap gradually and see the drift in the audit trail rather than discovering it in a hard cutoff.

The same trail answers the quieter questions a security analyst cares about. Which key tried to authenticate and failed, at what time, from which consumer. Rate limiting becomes forensics data when every event is written down.

## Failover: The Chaos Drill, Measured

Claims about resilience are worthless until something gets killed. So we killed it. The chaos drill runs against a live gateway in a single session with the primary serving real traffic:

```
primary alive  -> 200 glm-5.3-flash
chaos kill     -> 200 mock-fallback   (client saw nothing but a 200)
revive         -> 200 glm-5.3-flash
```

Three things make that sequence interesting rather than theatrical.

First, the failover is invisible to the client. The consumer sent an OpenAI shaped request and got a 200 back. It never learned that the backend it was supposed to hit died mid flight. From the client side, the gateway is the API, and the gateway stayed up.

Second, failback is automatic. When the primary came back, traffic returned to it on the next request, because the backend chain keeps health state current and ordering is always preferred first. Nobody ran a script, flipped a config, or restarted anything.

Third, the whole story is in the audit trail: the serve from the primary, the kill, the serve from the fallback, the revive, the return. When someone later asks why a response that afternoon came from the fallback model, the answer is a query, not an investigation.

## Why OpenAI Compatibility Is the Whole Game

The gateway could have invented a protocol. That would have been a mistake, and not just for convenience reasons.

OpenAI compatibility means the gateway is a drop in replacement anywhere the OpenAI SDK already works. Internal consumers migrate by changing one base URL. That keeps the migration cost near zero, which matters politically as much as technically: a gateway nobody adopts enforces nothing.

It also means the gateway is backend agnostic. Any server that speaks the protocol, whether that is vLLM on our own hardware or a hosted provider, can slot into the chain. Backend selection becomes a routing decision the platform makes, not a dependency each consumer owns. When a better or cheaper backend appears, it enters the chain and the policy decides who uses it.

The stable surface has a security benefit too. One authenticated front door means one place to enforce tenant isolation, one place to log, one place to revoke. Consumers never hold backend credentials at all. The gateway holds them, and the audit trail holds the gateway accountable.

## What Comes Next: Bastion and Per Tenant Attribution

Ball Knowledge is one step in a wider pipeline at Tech Guard: cost visibility, load testing, latency tracing, and now traffic policy. The next project, Bastion, builds directly on this foundation. It takes the per tenant identity the registry established and hardens it into sandboxed execution paths with full audit queryability. The per tenant attribution the gateway records is also what feeds real numbers into our cost dashboards, turning aggregate spend into attributable spend.

The broader lesson generalizes. Traffic policy, budget enforcement, and failover are not features you add to a platform later. They are properties the platform has or does not have from day one, and the cheapest place to build them is one shared layer in front of the backends. Build them once, prove them under chaos, and every consumer inherits them for free.

## Conclusion

Ball Knowledge gives Tech Guard a single OpenAI compatible surface for every internal model consumer, with per tenant rate limits, token budgets, and a complete audit trail enforced at the front door. The live chaos drill settled the question that usually stays unanswered: kill the primary and requests keep succeeding on the fallback, revive it and traffic returns, all without a client ever seeing an error. Resilience and cost control here are built in, not bolted on, and the design keeps every piece of state behind an interface so the system can grow without a rewrite. That is what we mean when we say production is a traffic policy, not one endpoint.

---

## Alternate Titles

1. Ball Knowledge: One API Surface, Zero Single Points of Failure
2. Your LLM Gateway Is a Traffic Policy, Not an Endpoint
3. Inside Ball Knowledge: Rate Limits, Token Budgets, and Failover That Survives a Chaos Drill

## X Hooks

- We killed our model backend mid request and the client got a 200 anyway. Ball Knowledge, our OpenAI compatible gateway, routed to the fallback in the same request and returned traffic when the primary revived. Chaos drills beat architecture diagrams.
- Production AI is not one endpoint, it is a policy: who spends what, who gets throttled, what happens when the primary dies. We built one gateway to enforce all of it, then killed the backend live to prove failover works.
