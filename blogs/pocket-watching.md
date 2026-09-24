# Pocket Watching: Every Dollar in the Inference Stack, Live

GPU spend is the easiest number on the team to lose track of and the hardest one to explain at the end of the month. Pocket Watching is Tech Guard's answer: a FinOps dashboard that scrapes live metrics straight off our vLLM cluster, computes cost per million tokens in real time, and breaks the spend down by tenant, model, and time window. A masthead of googly eyes on a brown leather wallet gives it personality. The numbers underneath stay dead serious.

## Why a monthly bill is the wrong unit of measurement

By the time a cloud invoice lands, the decisions that created it are weeks old. A tenant that quietly pinned a 70B model for embeddings, a batch job that retried through a GPU shortage, a prompt cache that never got warm: none of it is recoverable from a line item that says "inference, region us east."

FinOps for inference is fundamentally different from FinOps for storage or compute. A reserved instance bills whether you use it or not. A GPU serving tokens bills by the second, and the cost of any single request depends on the model, the sequence length, the cache hit rate, and how busy the cluster was. You need the number while the request is still in flight, not on the fifth of next month.

Pocket Watching makes cost a live operational signal, the same way latency and throughput are. Engineers open it before they open the logs.

## How the numbers get computed

The pipeline is deliberately boring. Every fifteen seconds, a scraper hits the vLLM metrics endpoints on each replica and pulls token counts, request counters, and cache statistics. A second job reads the node's GPU utilization from DCGM. Those samples land in a time series store, and a small service stitches them to a price table.

The core computation is straightforward:

```python
cost_per_mtok = (gpu_hour_rate / throughput_tokens_per_hour) * 1_000_000
```

The devil is in `throughput_tokens_per_hour`. Idle GPUs drag the denominator toward zero, so the dashboard tracks two numbers: marginal cost per million tokens when the GPU is busy, and effective cost including idle time. Both matter. Marginal cost tells you whether a model is priced sensibly. Effective cost tells you whether it should exist on the cluster at all.

Tenant attribution uses an API key to model mapping maintained alongside the gateway config, so every request rolls up to a payer without instrumenting client code.

## Breaking spend down the way people actually think about it

A single total is useless. Pocket Watching offers three axes, and each one answers a different question.

* **By tenant.** Which internal team or customer is driving the bill this week? This is the axis that prevents awkward conversations, because it turns "inference got expensive" into "tenant B's new agent workload tripled its long context traffic."
* **By model.** The 8B model might serve ten times the tokens of the 70B at a tenth of the cost each. Per model cost per million tokens makes routing decisions concrete: when the router sends a summarization job to the wrong tier, the dashboard shows it in dollars, not vibes.
* **By time window.** Hour, day, week, month views over the same data. The hour view catches incidents. The month view catches drift. The week view catches the slow creep where every model gets a little more traffic and nobody notices until the quarter closes.

The time window selector is the most used feature in practice. Cost anomalies are usually time shaped: a spike during a deploy, a ramp after a product launch, a weekend where a cron job forgot the cluster is smaller.

## What the vLLM metrics actually tell you about cost

Scraping vLLM directly is what makes the whole thing honest. The counters we lean on:

* `vllm:prompt_tokens_total` and `vllm:generation_tokens_total` give the raw token volume, split into prompt and completion. Prompt tokens are usually the bigger half for agent workloads, and they cost real money.
* `vllm:gpu_cache_usage_perc` is the proxy for prefix cache efficiency. A tenant whose cache usage sits near zero is paying full price to reprocess the same system prompt thousands of times. That single metric has paid for this project more than once.
* Queue depth and running request gauges explain the gaps. When cost per million tokens jumps, the cause is usually visible in the same scrape: preemption, retries, or a batch of very long sequences hogging the scheduler.

Because the metrics come from the serving layer, attribution survives routing changes and model swaps. There is no sidecar to maintain and no sampling to miss the expensive tail.

## Feeds from the rest of the portfolio

Pocket Watching does not live alone. Every other project in the Tech Guard portfolio publishes a small spend feed, and the dashboard rolls them into one view. The agent framework reports tokens consumed per workflow run. The training side reports checkpoint storage and reserved GPU hours. The data pipeline tags its embedding jobs with the same tenant keys.

The payoff is a single pane where the question "what did we spend on this project last week" has one answer. Portfolio feeds also catch cross project effects: when a new project's eval harness starts hammering the shared cluster, Pocket Watching shows the cost landing on the tenants that share the GPUs with it, not just on the project's own line.

Integration is one config entry and a weekly aggregation endpoint. If a project can emit a number with a tenant key and a timestamp, it belongs in the feed.

## The googly eyes are load bearing

The masthead is a brown leather wallet with a pair of googly eyes. That is not a design flourish; it is a deployment strategy. Dashboards die when nobody opens them. A page that makes people smile gets opened, and a page that gets opened gets trusted, and a page that gets trusted becomes the place where cost arguments get settled.

The personality is in the masthead only. Every chart, every table, and every number is exactly as serious as the money it represents. If a number looks wrong, an engineer can click through from the cost series to the raw vLLM counters and the price table in two steps. Trust in a FinOps tool comes from being able to check its work.

## Conclusion

Pocket Watching turned GPU spend at Tech Guard from a monthly surprise into a live number that anyone on the team can open, understand, and act on. The design that got it there is simple: scrape the source of truth directly, compute cost per million tokens with and without idle time, attribute every token to a tenant, and make the page pleasant enough that people actually look at it.

If you run your own inference stack, the cheapest version of this is an afternoon: one scraper against your vLLM metrics, one price table, one chart. You will find something surprising in the first hour. The full version, with tenant attribution and portfolio feeds, is what we run every day at Tech Guard, and it is the reason our infrastructure reviews start with facts instead of estimates.

---

## Alternate Titles

1. Pocket Watching: The Dashboard That Knows What Every Token Costs
2. We Stopped Guessing at GPU Spend, So We Built Pocket Watching
3. Cost per Million Tokens, Live: Inside Pocket Watching

## X Hooks

1. Our GPU bill used to be a monthly surprise. Now it's a live number anyone on the team can open. Pocket Watching scrapes vLLM metrics every 15 seconds and prices every token by tenant, model, and hour. The googly eyed wallet is optional. The number is not.
2. The most expensive prompt in your stack is the one you reprocess a thousand times with a cold prefix cache. We built Pocket Watching to catch exactly that, in dollars, in real time. FinOps for inference is an ops problem, not an accounting problem.
