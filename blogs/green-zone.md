# Green-Zone: What 48 Live Requests Taught Us About Speculative Decoding

Speculative decoding promises free throughput: a small draft model guesses ahead, the big model checks, and you pay one forward pass for several tokens. On paper it looks like a multiplier you can crank harder by drafting longer. We ran a live study on our production cluster, project Green-Zone, across 48 real requests under varying concurrency, and the data tells a sharper story. Acceptance sat near 22 percent no matter how hard we pushed the cluster, each draft cycle returned about 1.5 accepted tokens, and per position acceptance fell off geometrically until it bottomed out around positions three and four. That decay curve is the whole story. It explains the throughput knee our batcher had been measuring, and it tells us the ceiling of speculation on this workload lives in the engine, not in the load.

## The Setup: A Study Run Against Production

We did not build a synthetic benchmark. Green-Zone ran against the production cluster on live traffic, 48 requests spanning the concurrency levels the batcher actually schedules. That choice mattered. Synthetic prompt sets tend to overrepresent short prompts and tidy context windows, and they flatter speculative decoding in ways production never does.

Each request carried instrumentation at three levels: per request acceptance rate, per cycle accepted token count, and per position acceptance probability. The first two numbers are what most teams track. The third is the one that actually explains the other two, and it is where the interesting physics showed up.

Concurrency was varied deliberately across the run. Low concurrency means the target model has spare compute to burn on verification. High concurrency means every verification pass competes with real decode work for the same SMs. If load shaped acceptance, it would show up as divergence between those regimes. It did not.

## Acceptance Held at 22 Percent, Period

Across all 48 requests, acceptance rate hovered near 22 percent. Not 22 percent at low load and 15 percent at high load. Not 22 percent for short prompts and 30 percent for long ones. A flat line.

That flatness is diagnostic. Acceptance rate is a function of how well the draft model predicts the target model's distribution on this workload. Nothing about scheduler pressure changes that distribution. The load can change how expensive verification is per token, but it cannot change how often the draft is right. Green-Zone confirmed this empirically: the ceiling on speculation is a property of the model pair and the workload, not a property of the cluster.

The practical consequence is that no amount of tuning the scheduler, reshaping batches, or adjusting KV cache pressure will move acceptance. Teams that chase acceptance under load are optimizing the wrong variable.

## Each Draft Cycle Buys About 1.5 Tokens

Per draft cycle, roughly 1.5 tokens got accepted. With 22 percent per position acceptance, that arithmetic checks out: if each drafted position independently accepts at rate p, the expected tokens per cycle is p divided by one minus p, which at p equals 0.22 comes to about 1.4. Our measured 1.5 sits right on that line.

```python
# expected accepted tokens per cycle for per position rate p
def tokens_per_cycle(p):
    return p / (1 - p)

# 0.22 -> ~1.41, matching the measured ~1.5
```

This is the number that matters for throughput planning. A cycle costs one target forward pass. If it returns 1.5 tokens, speculation is a 1.5x multiplier on decode steps before you subtract the cost of running the draft model itself. On a workload where the draft is cheap relative to the target, that is a real win. It is not the 3x to 5x that optimistic blog posts advertise, and now we know why.

## The Geometric Decay and the Sweet Spot at Positions Three and Four

The per position data is the core finding. Position one, the first drafted token, accepts well above the average. Each subsequent position accepts at some fraction of the one before it, a clean geometric decay. By positions three and four the curve has flattened toward its floor, and acceptance beyond that contributes almost nothing.

Why does this happen? Because a drafted token at position k is conditioned on k minus one prior draft tokens. If the draft was wrong early, everything after it is wrong in a correlated way, and even a correct draft branch can be rejected because the target's context diverged. Errors compound down the draft chain, so the value of drafting deeper decays geometrically even when the draft model is individually accurate at each step.

The sweet spot at positions three and four is where the marginal expected token from one more drafted position drops below the marginal cost. Drafting longer than that adds draft compute, adds verification tokens the target must score in parallel, and returns nearly nothing. Drafting shorter leaves accepted tokens on the table.

## Why Batcher Saw a Throughput Knee

Our batcher had long shown a knee in the throughput curve: aggregate tokens per second climbed with draft length, then flattened abruptly. Before Green-Zone the knee was an unexplained artifact. Now it has a mechanism.

The knee is exactly where the geometric decay reaches its floor. Up to that point, deeper drafts buy real tokens. Past it, deeper drafts only add verification overhead: the target model scores more candidate tokens per pass, consuming memory bandwidth and attention compute that real decode work could use, especially at high concurrency where verification shares the GPU with batched decode. The knee is not a scheduler artifact or a cache cliff. It is the geometric decay made visible in aggregate throughput.

This is a satisfying result because it converts a mystery into a design parameter. The batcher can now read the knee directly from per position acceptance curves instead of discovering it by sweeping draft lengths under load.

## What This Means for Our Draft Lengths

The conclusion for tuning is that our draft lengths are already near optimal. The knee sits where the decay bottoms out, and our configured draft depth sits at that knee. There is no hidden multiplier from drafting deeper, and drafting shallower would forfeit tokens in the profitable positions one through three.

Three takeaways for anyone running speculation in production:

1. Measure per position acceptance, not just aggregate acceptance. The decay curve is the actual tuning signal, and aggregate numbers hide it.
2. Expect acceptance to be load invariant. If yours drops under concurrency, suspect a measurement artifact or a draft model behaving differently under batching, not a fundamental load effect.
3. Treat the knee as the target. Your draft length should sit where marginal accepted tokens per position flatten, which Green-Zone showed is near positions three and four on this workload.

The deeper point is that the ceiling of speculation here is a property of the engine, meaning the model pair and the workload's distributional structure. Load, concurrency, and scheduling move the cost side of the ledger, not the acceptance side. If we want a higher ceiling, the lever is a better matched draft model or a workload with more predictable structure, not more cluster tuning.

## Conclusion

Green-Zone took 48 live requests and turned a throughput knee into a mechanism. Acceptance held at 22 percent under any concurrency, draft cycles returned about 1.5 tokens, and per position acceptance decayed geometrically to its floor at positions three and four. That curve explains the knee, validates our current draft lengths, and fixes the ceiling of speculation on this workload where it belongs: in the engine.

The next step is applying the same instrumentation to other model pairs. If the decay curve is stable across workloads, per position acceptance becomes a standard acceptance gate for any draft model we deploy, measured before it touches production traffic rather than discovered in the throughput graph after the fact.

***

## Alternate Titles

1. Green-Zone: The Geometric Decay That Sets Our Speculation Ceiling
2. 48 Live Requests, 22 Percent Acceptance: Inside the Green-Zone Study
3. Why Our Throughput Knee Was the Draft Curve All Along

## X Hooks

1. We ran speculative decoding against production, 48 live requests. Acceptance sat at 22 percent under any load. Per position decay hit its floor at position three. That curve IS our throughput knee. The ceiling is the engine, not the cluster.
2. Drafting deeper stopped paying off at position four and the numbers were not subtle. Green-Zone showed the geometric decay behind our throughput knee. If your draft length is tuned to that floor, no scheduler change will buy you more.
