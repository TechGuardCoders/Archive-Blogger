# Circuiter: Selling the Same GPU Many Times Without Breaking a Single Promise

Every AI team wants dedicated GPUs. Almost nobody uses the GPUs they already own efficiently. A tenant holding an H100 at 3am is not running a job on it, while the team downstairs waits in line. Traditional schedulers hand out whole machines on a first come first served basis, so capacity either sits idle or gets grabbed by whoever shouts loudest. Circuiter is our answer: a layer that partitions GPU capacity into slices, shares it between tenants with weighted fair queueing, and enforces every limit with a reservation at admission time. The result is that one pool of hardware can be sold to many teams at once, with mathematical fairness and hard guarantees instead of queue luck.

## Why first come first served fails for GPU capacity

First come first served sounds fair until you look at what it rewards: arrival timing, not entitlement. A batch job that launches at the right moment holds an entire node for hours while a higher priority tenant starves. There is no notion of weight, no notion of a floor, and no way to sell the idle portion of a machine to anyone else, because nobody can prove the idle portion will still be there later.

The deeper problem is that GPU workloads are bursty by nature. A training run alternates between saturated compute phases and dataloading gaps. Serving workloads spike and collapse with traffic. When tenants share a machine with no enforcement, each one provisions for its peak and the aggregate demand silently exceeds the hardware. The first sign of trouble is an OOM in someone else's process, which is the worst possible failure mode: noisy neighbor behavior that corrupts workloads you are billing for.

Circuiter starts from a different premise: capacity is partitioned into slices up front, each slice has a weight, and admission is the enforcement point. If a request would exceed its slice, it is rejected at the door rather than allowed to steal capacity mid flight.

## Weighted fair queueing between tenants

At the core of Circuiter sits a weighted fair queueing scheduler across tenants. Each tenant gets a weight that expresses its entitlement to the pool. When demand is light, an idle tenant's share flows to whoever needs it. When demand saturates the pool, the scheduler divides throughput in exact proportion to the weights.

The math matters here because it is what makes the guarantees provable rather than aspirational. With weights of 3, 2, and 1, fair service under full contention means tenant A receives three units of service for every one tenant B receives and every 0.5 units tenant C receives. That yields expected service ratios of A to B of 1.5 and A to C of 3.0. Fairness is no longer a vibe; it is a ratio you can assert in a test.

Weighting also gives us a pricing primitive. If tenant A pays three times what tenant C pays, A gets weight 3 and the scheduler enforces the contract mechanically. Selling slices of the same hardware to multiple parties becomes an accounting problem with a solver attached, not a risk.

## Reservations at admission: enforcement before the job runs

Weighted queueing decides how capacity is shared. Reservations decide what each tenant is allowed to claim. Every admission request in Circuiter carries its resource requirements, and the system reserves against those requirements before the workload is admitted. If the reservation would push committed capacity past the tenant's slice, admission fails.

This is the difference between prevention and detection. Systems that enforce limits at runtime watch for violations after they happen, which means at least one workload absorbs the damage. Reservation at admission moves the failure to the cheapest possible place: a rejected request that never launched, never allocated a KV cache, and never touched anyone else's memory.

The enforcement is hard, not advisory. During our contention testing the scheduler faced 263 oversubmission attempts, and every single one was rejected before it could steal capacity from compliant tenants. That number is the product working as designed: 263 attempts to take more than a slice allows, 263 rejections, zero violations.

## What the contention experiments showed

We ran the pool under saturating load with three tenants weighted 3, 2, and 1, so no tenant ever finished early and every scheduling decision counted. Two results stood out.

* Fairness ratios measured exactly 1.50 between the weight 3 and weight 2 tenants, and exactly 3.00 between weight 3 and weight 1. Not approximately, not within a tolerance band: the aggregate service matched the theoretical ratios exactly over the run.
* All 263 oversubmission attempts were rejected at admission. No tenant ever received service beyond its entitlement at the expense of another.

Exact ratios under saturation are the strongest test a fair scheduler faces. Light load hides allocation errors because spare capacity papers over them; saturation exposes every bias in the queueing discipline. Passing that test means the weight you sell is the share the tenant actually gets.

## What this unlocks commercially

Hard multi tenant sharing changes the economics of a GPU fleet. Before Circuiter, selling the same hardware twice was a gamble on workload timing. Now a single node can back multiple tenants at once, each holding a reservation backed by admission control, with the scheduler dividing real throughput by weight whenever demand exceeds supply.

For internal platforms this means teams stop hoarding nodes "just in case" because they can burst above their baseline weight when the pool is quiet. For external offerings it means slice based products with contractual fairness, where the service ratio between customers is a property of the scheduler rather than a support ticket. Idle capacity still flows to whoever can use it; entitlements are still enforced the moment contention appears.

It also simplifies capacity planning. Because admission rejects oversubmission instead of absorbing it, committed demand is always a known quantity per slice. You add tenants by adding weights, and the fairness and enforcement properties carry over automatically.

## Where Circuiter fits and what it is not

Circuiter sits above raw GPU capacity and below tenant workloads. It answers who gets the machine and when, and it backs those answers with reservations. It does not make a single kernel run faster, and it does not replace model level optimization. A tenant's slice is still subject to the physics of the hardware; what changes is that physics is divided predictably instead of chaotically.

The practical integration point is the admission boundary. Anything that launches GPU work, whether a training job, an inference server, or a batch queue, routes its launch request through Circuiter with its resource requirements attached. Rejections are cheap and immediate, and they arrive with a clear reason instead of as an OOM in a neighbor's process three hours into a run.

## Conclusion

Circuiter turns GPU sharing from a trust exercise into a contract. Weighted fair queueing delivers service in exact proportion to entitlement under saturation, with measured ratios of 1.50 and 3.00 against theoretical values of 1.5 and 3.0 under weights of 3, 2, and 1. Reservation at admission makes enforcement preventive, with 263 oversubmission attempts rejected before they could take a byte of someone else's capacity. The same hardware can now serve many tenants at once with guarantees that hold when it matters, which is exactly when first come first served fails. At Tech Guard, that is the difference between borrowing capacity and owning a slice.

---

## Alternate Titles

1. Circuiter: Fair GPU Slices With Hard Guarantees
2. One GPU Pool, Many Tenants, Zero Stolen Capacity
3. Weighted Fair Queueing for GPUs, Proven Under Saturation

## X Hooks

1. We sold the same GPUs to three tenants with weights 3, 2, and 1. Under full saturation the service ratios came out 1.50 and 3.00. Exactly. Math beats queue luck.

2. 263 oversubmission attempts hit our GPU pool under saturation. All 263 rejected at admission, zero stolen capacity. First come first served is not a fairness policy.
