# Flunk: We Killed a Region on Purpose and Got Real Recovery Numbers

Every disaster recovery plan looks great until something actually breaks. Runbooks promise failover in seconds, dashboards claim high availability, and architecture diagrams show resilient multi region topologies. None of that is evidence. It is aspiration written by people who were not being paged at the time.

Flunk is Tech Guard's failover drill harness. It runs two real HTTP regions behind a health driven router, kills one of them on demand, and measures exactly what happens. Not a simulation, not a mock: real processes serving real requests, with one region abruptly taken out. The output is a set of numbers you can put in a slide deck and defend under questioning.

## Why Failover Needs Rehearsal, Not Documentation

A failover path is code, and untested code is broken code with better marketing. The failure modes that matter are never the ones in the diagram. Health checks that report healthy for a dead backend. Connection pools that pin to a region that stopped existing. Clients that cache DNS long past the point of usefulness. Load balancers that flip back and forth between a live region and a dying one.

You cannot find any of that by reading config. You find it by sending production shaped traffic through a topology where you control the failure, then looking at what actually returned 200s. The gap between "we have failover" and "failover works" is only measurable during an outage, so Flunk manufactures outages at a time of our choosing instead of waiting for a Tuesday at 3 AM to choose for us.

## The Architecture: Two Regions and a Router That Counts

Flunk runs two genuine HTTP regions, each a full service with its own process, port, and health endpoint. In front of them sits a router whose job is simple: send traffic to the primary, and move to the secondary only when the primary proves unhealthy. All routing decisions come from health state, not from config files or manual switches.

The router does not react to a single failed probe. Two thresholds govern every transition:

- **Failure threshold: 3 misses.** A region is declared down only after three consecutive failed health checks. One dropped probe or one slow response does not trigger a failover.
- **Recovery gate: 3 hits.** A recovered region is promoted back to primary only after three consecutive successful health checks. A backend that boots, hiccups, and dies again never makes it back into rotation.

Those two gates exist to solve the same problem from opposite directions: flapping. Without the miss threshold, a single lost heartbeat yanks traffic to the secondary and back, multiplying user visible errors. Without the recovery gate, a half healthy region gets promoted, fails again, and the router oscillates. Hysteresis on both sides of the state machine is what turns "reacts to failure" into "stable under failure."

## The Live Kill: What We Measured

With both regions healthy and load flowing, we terminated the primary outright. No graceful shutdown, no draining. Here is what the harness recorded:

- **Recovery time objective: 1.1 seconds.** From kill to steady state traffic on the secondary, the outage window lasted 1.1 seconds.
- **Recovery point objective: 2 lost requests.** Exactly two in flight requests died with the process. Everything after the failover completed normally.
- **Availability through the outage: 18 of 20 requests served.** During the drill window, 90 percent of traffic never saw an error.
- **Clean return to primary.** Once the region healed and passed the three hit gate, traffic shifted back and the secondary returned to standby without manual intervention.

The 1.1 second RTO is arithmetic you can check: three missed probes at the probe interval, plus the routing switch, plus the first successful request on the secondary. Nothing about it is luck. If we need a tighter number, we know exactly which knob to turn, and what flapping risk that tighter interval buys.

The RPO of 2 lost requests deserves equal attention. That is the honest cost of the kill: whatever was mid flight when the process died. Flunk makes that cost visible instead of letting "we have replication" imply that data loss is zero. Zero is a claim; 2 requests is a measurement.

## Why Thresholds Beat Speed

The instinctive design goal for failover is speed: detect failure instantly, switch instantly. Flunk's design says the real goal is correctness at a speed good enough for your users. A router that fails over in 200 milliseconds on any transient blip will produce more total downtime than one that waits 1.1 seconds for three consecutive misses, because false failovers are outages too.

The three hit recovery gate is the half of the design most teams skip. Without it, a region recovering from a real incident boots into rotation, falls over under load, and triggers a second outage minutes after the first. Waiting for three clean health checks costs a fraction of a second and eliminates the most common repeat outage pattern in multi region systems. Slow to promote is cheap; fast to promote wrongly is expensive.

## What the Drill Proves That Docs Cannot

A successful Flunk run is a chain of verified claims: the health checker detects real death, the router stops routing to it, the secondary absorbs full traffic, in flight loss is bounded and counted, recovery is detected, and promotion back happens without a human. Each link in that chain is exercised against real HTTP, not asserted in a wiki page.

It also produces a regression harness. When someone changes probe intervals, connection handling, or routing logic, the drill runs again and the numbers either hold or they do not. Failover behavior becomes a testable property of the system instead of a folklore belief passed between oncall engineers. The numbers from the last drill are quoted in design reviews; the numbers from a hope are not.

For teams where availability targets are contractual, this is the difference between "our SLO is 99.9 percent" and "we killed a region and served 18 of 20 requests with a 1.1 second RTO." One of those sentences survives an audit.

## Conclusion

Flunk turns failover from a promise into a rehearsed, measured behavior. Two real regions, a health driven router with a three miss failure threshold and a three hit recovery gate, and a kill switch that produces hard numbers: 1.1 second RTO, 2 lost requests, 18 of 20 requests served through the outage, and a clean return to primary.

The broader lesson is that outage response is a muscle, and muscles only grow under load. Tech Guard runs its own private AI lab and rehearses failure on demand, which means when a real outage arrives we quote recovery numbers we have already earned rather than numbers we merely hope for. If your recovery plan has never been executed against a live kill, its RTO is a rumor.

---

## Alternate Titles

1. Flunk: Real Failover Numbers From a Region We Killed on Purpose
2. Three Misses, Three Hits: How Flunk Rehearses Multi Region Failure
3. Your RTO Is a Guess Until You Kill a Region: Meet Flunk

## X Hooks

1. We killed our primary region on purpose. Result: 1.1s failover, 2 lost requests, 18 of 20 requests served through the outage, clean return to primary. That is a measured RTO, not a hopeful one.

2. Failover you have never tested is just a rumor in your runbook. Flunk kills real regions on demand so we can quote recovery numbers we actually earned.
