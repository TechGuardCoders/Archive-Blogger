# Batcher: Measuring What Concurrency Actually Does to Throughput

Every serving stack has a story about concurrency, and most of those stories are wrong. Someone assumes doubling concurrent requests doubles throughput. Someone else caps the cluster at two requests per replica because a benchmark from another model said so. Batcher exists to replace that folklore with a curve measured on our own production serving stack. The question is simple: as concurrent requests grow, how does aggregate throughput actually behave? The answer turned out to be more interesting than a straight line, and the bend in that line pointed straight at speculative decoding.

## The Numbers

Batcher measures aggregate throughput, not per request latency. That distinction matters. When we ramped concurrency on the production stack, the numbers moved like this:

| Concurrency | Aggregate throughput (tokens per second) |
| --- | --- |
| 1 | 43.8 |
| 2 | 45.2 |
| 4 | 67.9 |

Read that table from the top and the shape jumps out. Going from one to two concurrent requests bought almost nothing: 1.4 tokens per second, roughly three percent. Going from two to four bought 22.7 tokens per second, a jump of nearly fifty percent. If throughput scaled linearly with concurrency, the two request number should have landed around eighty or ninety. Instead it barely moved. There is a clear knee at two, and the knee is the whole story.

## Why the Knee at Two Is the Signal

A knee like that is never random. It means some mechanism that pays off at low concurrency starts costing more than it earns. In this stack, that mechanism was speculative decoding.

Speculative decoding trades compute for latency. A cheap draft model proposes several tokens at once, the large model verifies them in a single forward pass, and accepted tokens skip the serial decode loop entirely. At concurrency one, that trade is almost free: the GPU has idle capacity, verification rides along, and end to end latency drops sharply. But speculative decoding changes the shape of each batch. A batch of two requests running speculation is effectively four sequences in flight, because each request carries a draft. The verifier processes both the draft tokens and the correction work, so the memory bandwidth and compute budget that batching would spend on real requests gets spent on guesses instead.

That is exactly what the curve shows. At concurrency one, speculation is a win and there is spare capacity to pay for it. At concurrency two, the speculation overhead eats nearly all of the gain batching would otherwise deliver. At concurrency four, real request batching finally overwhelms the overhead and throughput climbs properly. The knee is the point where the overhead and the batching gain cancel out.

## Truffle Confirmed It

A single measurement is a hypothesis. Batcher flagged the knee, and Truffle, our internal analysis pass, went and confirmed the mechanism. Truffle instrumented the serving stack to attribute GPU time across the decode phases. The breakdown showed what the curve implied: at higher concurrency, a growing share of forward passes was spent verifying draft tokens rather than producing useful output, and the draft acceptance rate did not improve enough to justify that share.

This is the pattern we care about at Tech Guard. A throughput curve tells you where to look. An attribution pass tells you what you found. Neither alone is enough. The confirmation mattered because the obvious fix, disabling speculative decoding, would have helped at high concurrency while quietly hurting every single user request at low concurrency. Knowing the mechanism lets you make the tradeoff deliberately instead of flipping a flag and hoping.

## How We Use These Curves in Production

The throughput curve is not a chart on a wall. It drives two concrete decisions on the serving side.

First, request limits. Each replica gets a concurrency cap set just past the knee of its curve, not at it. For this stack that means allowing more than two in flight requests per replica, because the data shows the region between two and four is where throughput actually pays off. Capping at the knee would be capping at the worst point on the curve.

Second, capacity expectations. The curve is the contract for what the cluster can absorb before latency suffers. Ops knows that a replica absorbing four concurrent requests delivers about 67.9 tokens per second of aggregate work. When projected load multiplies that number past the fleet total, we know we are adding replicas, not tuning. The curve converts "the cluster feels slow" into a numeric headroom figure.

The practical recipe, should you want to reproduce this:

```python
for c in [1, 2, 4, 8]:
    run_load_test(concurrency=c, duration="5m")
    record(c, measured_tokens_per_second)
```

Keep the concurrency ladder exponential. Linear steps hide knees, because a knee between two sampled points looks like noise. Exponential steps make every mechanism change show up as a visible bend.

## What the Knee Costs You If You Miss It

Miss the knee and you make one of two expensive mistakes. Cap concurrency at two and you leave forty percent of your cluster throughput on the table, which means paying for GPUs that idle while a queue forms. Remove speculative decoding to chase high concurrency numbers and your latency for interactive, single user sessions degrades, which is the regression users actually notice.

The deeper lesson is that optimizations compose badly. Speculative decoding is a latency optimization. Continuous batching is a throughput optimization. Neither is free, and their costs overlap in the same resource: per forward pass compute and memory bandwidth. Stacking two optimizations without measuring the stack is how you end up with a system where each feature benchmarks well alone and the combination underperforms both. Batcher exists precisely to catch that class of failure before it reaches a capacity planning spreadsheet.

## Conclusion

Batcher started as a load test harness and ended up as a diagnostic instrument. The curve it produced, 43.8 to 45.2 to 67.9 tokens per second at concurrency one, two, and four, contained a knee that looked like a measurement artifact and turned out to be the signature of speculative decoding overhead, a finding Truffle later confirmed by attributing GPU time directly. The takeaway for anyone running a serving stack: measure throughput across a concurrency ladder before you set request limits, treat every bend in the curve as a mechanism asking to be identified, and never let two optimizations share a resource budget without checking whether they are fighting. The cluster tells you the truth. You just have to sample it at the right points.

---

## Alternate Titles

1. The Knee at Two: What Concurrency Actually Does to LLM Throughput
2. Batcher: Finding the Concurrency Knee That Speculative Decoding Hid
3. 43.8, 45.2, 67.9: A Throughput Curve That Changed Our Request Limits

## X Hooks

1. Throughput at concurrency 1, 2, and 4: 43.8, 45.2, 67.9 tokens per second. Doubling requests bought 3%. Doubling again bought 50%. That knee was speculative decoding eating the batch. Measure the curve before you set request limits.

2. Two optimizations, one GPU: speculative decoding for latency, batching for throughput. Alone, each wins. Together, the knee in our curve showed them canceling out. We found it with a load ladder, confirmed it with attribution. Your cluster is telling you the same thing.
