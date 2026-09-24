# Spinal: Phase Tracing That Shows Where Inference Time Actually Goes

Latency dashboards tell you that p99 got worse. They never tell you why. Spinal is a phase tracing tool that splits every inference request into its stages: queue wait, tokenization, prefill, decode, post processing, and network egress. Each phase gets its own timer, and every request carries those timings back to a central trace store. The result is a request level map of where milliseconds go, not a single latency number with a shrug attached.

Under load, Spinal did exactly what it was built to do. It exposed a 38 times jump in queue wait between concurrency two and concurrency four, and a drift factor of 1.476 against a tolerance of 1.25. Both findings came from phase data, not intuition. Both changed how Tech Guard plans capacity.

## Why Average Latency Hides the Real Problem

A typical inference service reports latency as one number per request. When that number climbs, you know something degraded, but you cannot tell which stage absorbed the delay. Queue wait and decode speed produce identical looking spikes on a summary dashboard, yet they demand completely different fixes. One is a scheduling problem, the other is a memory bandwidth or batch size problem.

Averages make this worse. A request that waits 900 milliseconds in a queue and decodes quickly looks the same as a request that never queued and decoded slowly. Spinal refuses to collapse those cases together. Every phase is measured independently, so the two failure modes stay distinct and actionable.

The same applies to percentiles. p99 latency tells you that the worst requests exist. It cannot tell you that most of their extra time came from prefill contention after a batch size change last Tuesday. Phase traces can.

## How Spinal Breaks a Request Into Phases

Spinal instruments each hop in the inference path and records a timestamp at every boundary:

1. **Queue wait.** Time between the request arriving and the engine accepting it.
2. **Tokenization.** Turning the raw prompt into token ids, including any preprocessing.
3. **Prefill.** The forward pass over the full prompt before the first output token.
4. **Decode.** Autoregressive generation, one forward pass per token until stop.
5. **Post processing.** Detokenization, filtering, and any response shaping.
6. **Egress.** Serialization and network transfer back to the caller.

Each request emits a compact trace object. A minimal entry looks like this:

```json
{
  "request_id": "a91f2c",
  "queue_wait_ms": 412.3,
  "tokenize_ms": 3.1,
  "prefill_ms": 58.7,
  "decode_ms": 210.5,
  "post_ms": 4.2,
  "egress_ms": 1.8
}
```

Because phases are tagged per request, Spinal can slice by model, batch size, concurrency level, prompt length, or time of day. That slicing is what turns raw timings into diagnosis.

## Finding One: The 38 Times Queue Wait Jump

The headline result came from a load test sweep across concurrency levels. At concurrency two, queue wait was negligible. At concurrency four, queue wait exploded by a factor of 38. Nothing about the model changed. Nothing about the hardware changed. Only the number of simultaneous requests moved, and the queue absorbed the entire difference.

This is a classic saturation signature. Between two and four concurrent requests the serving path crossed a capacity threshold, likely a scheduler slot, a KV cache limit, or a batch window that fills and then blocks arrivals. End to end latency metrics would have shown a smooth looking curve. Spinal showed the cliff, and it showed exactly which phase owned the cliff.

The practical takeaway: a service that looks healthy at low concurrency can be catastrophically oversubscribed one step above it. You only find that threshold by measuring queue wait as its own phase, and you only fix it by addressing scheduler or cache capacity, not by adding client retries that make the queue longer.

## Finding Two: Drift Factor 1.476 Against a 1.25 Tolerance

Spinal also tracks drift, the ratio between observed phase durations and expected durations under current load. Tech Guard sets tolerance bands on each phase so drift above a threshold triggers review before users notice. In this run, overall drift hit 1.476 against a tolerance of 1.25. The system was running roughly 18 percent over its allowed degradation envelope.

Drift matters because it catches slow decay that load tests miss. Memory fragmentation, cache eviction pressure, and background jobs erode performance gradually. Each individual change looks acceptable. Stacked together, they push real latency past the line. A drift factor is a single number that says how far the system has slid, and Spinal attributes that slide to the phases responsible.

The response to a drift breach is targeted: if drift concentrates in decode, look at KV cache pressure and batch composition. If it concentrates in prefill, look at prompt length distribution and scheduler policy. Spinal makes that attribution automatic instead of archaeological.

## From Vibes to Evidence in Capacity Planning

Before Spinal, capacity conversations at Tech Guard went roughly like this: users say the service feels slow, engineers guess at a cause, someone proposes a bigger instance, and nobody can prove the bigger instance helps. That loop wastes money when the guess is wrong and wastes weeks when the argument over the guess runs long.

With Spinal, the conversation starts from a trace. A claim like "decode is the bottleneck" comes with the phase breakdown that proves it. A claim like "we need another replica" comes with the queue wait curve showing exactly where saturation begins. Procurement, engineering, and leadership argue over numbers instead of adjectives.

Two concrete rules emerged:

1. **Scale the phase, not the box.** If queue wait owns the delay, more replicas help. If decode owns it, a bigger replica may not help at all.
2. **Set a drift budget per phase.** Aggregate tolerances hide where degradation lives. Per phase budgets localize it.

## What This Means for AI Infrastructure Teams

If you operate inference at any scale, phase tracing is the cheapest observability investment available for the information it returns. A model can appear 20 percent slower for a dozen different reasons, and each reason points to a different owner: the scheduler, the tokenizer, the network, the cache. Without phase data, every latency incident is a group guessing exercise.

Start by instrumenting the phase boundaries you already have. Most serving stacks expose timestamps at arrival, first token, and completion. Splitting first token latency into queue plus prefill takes a small amount of plumbing and immediately answers the most common question users ask: is the system busy, or is the model slow?

Spinal is now part of the standard toolchain Tech Guard runs for every inference deployment. The 38 times queue jump and the 1.476 drift factor were found in days, not weeks, and both would have been invisible in an aggregate latency chart. That is the whole point.

## Conclusion

Spinal turns latency from a feeling into a breakdown. Every request reports where its time went, load tests expose the exact concurrency where phases saturate, and drift factors flag gradual decay before users feel it. Tech Guard now runs capacity conversations with evidence attached: the phase that saturates is named, measured, and owned. When the next "responses feel slow" report lands, the first move is a Spinal trace, not a guess.

***

## Alternate Titles

1. Spinal: The Phase Tracer That Found a 38 Times Queue Wait Cliff
2. Stop Guessing Why Inference Feels Slow: Phase Tracing With Spinal
3. Drift Factor 1.476: How Spinal Turns Latency Into Evidence

## X Hooks

1. Inference latency is not one number. Spinal breaks every request into phases, and found queue wait jumping 38 times between concurrency two and four. The box was never the problem. The scheduler was.

2. Drift factor 1.476 against a 1.25 tolerance means your inference stack is 18 percent past its degradation budget. Phase tracing shows exactly which phase slid and when. Evidence beats vibes.
