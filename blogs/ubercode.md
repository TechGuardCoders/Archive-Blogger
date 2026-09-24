# UberCode: Model Weight Delivery With Content Addressed Shards

Moving model weights is a solved problem right up until it is not. A 100 megabyte checkpoint feels trivial until you are restarting servers twenty times a day, resuming downloads across flaky links, or paying for the same bytes twice because two teams staged identical weights under different names. UberCode is our answer: a model weight delivery system built on content addressed shards, where every byte pulled is verified and every byte already present stays untouched.

This post walks through the design, the numbers from a real cold bring up, and the failure modes the content addressed approach eliminates by construction.

## Why Shard Model Weights At All

A monolithic weight file is the worst possible unit for transport. It is all or nothing: a dropped connection at 95 percent means starting over, and verifying integrity means hashing the entire file before you trust a single byte. Sharding splits the blob into fixed size pieces that can be fetched in parallel, verified independently, and cached per shard.

UberCode shards a model into pieces sized for parallel transport. A 100 megabyte model becomes 12 shards. Each shard is hashed on write, and the hash becomes its identity on the network. There is no filename to trust, no manifest version to drift out of sync. If the hash matches, the shard is correct. If it does not, it gets discarded and refetched. Trust comes from the data itself.

The practical consequence is that partial state is always valid state. Whatever shards you have on disk after an interruption are good shards. That single property drives most of what follows.

## Content Addressing: The Hash Is The Name

Every shard in UberCode is named by the SHA 256 hash of its bytes. A model manifest is then just an ordered list of shard hashes. This is the same idea that powers Git and CAS storage systems, applied to weight distribution.

The payoff shows up in three places:

- **Verification is free.** You cannot download a shard without also confirming its hash, because the hash is the address. The 1.34 second cold bring up we measured included verification of every single shard. There is no separate integrity pass, no post download scan.
- **Deduplication is automatic.** Identical bytes anywhere in the system collapse to one stored shard. Two model variants that share a base checkpoint share its shards without any coordination.
- **Caching is exact.** A warm start diffs the manifest against local storage and pulls zero bytes, because every hash is already present. No staleness heuristics, no last modified timestamps, no conditional GETs that lie.

## The Numbers: Cold Bring Up In 1.34 Seconds

The headline measurement: a cold bring up of a 100 megabyte model across 12 shards completed in 1.34 seconds, with every shard hash verified on arrival. The shards were pulled in parallel, each verified independently, and assembled into the final model with no additional validation step.

For comparison, a naive single stream download of the same model with a follow up integrity check would serialize transfer and verification, and any interruption throws away everything. UberCode's cold path is fast because verification is woven into the transport rather than stacked after it.

The warm case is where the design really pays. A restart against an already populated cache issues a manifest comparison and pulls zero bytes. Bring up time drops to local disk reads. Restarting a model server during development stops being a decision you weigh against a coffee break.

## Resumption Without Waste

Interrupted downloads are where traditional distribution burns the most time. UberCode's resume logic is trivially correct because of addressing: compare the target manifest against what is on disk, and fetch only the hashes that are missing.

There is nothing to checkpoint, nothing to track. The local cache is the progress state. If a pull dies at shard 9 of 12, the next attempt fetches exactly 3 shards. If the network flips and a fetched shard fails verification, only that shard is refetched. Recovery cost is proportional to what is missing, not to the size of the whole model.

For anyone operating across regions, spot instances, or CI runners that come and go, this turns weight delivery from a reliability problem into a rounding error.

## Deduplication As A Bug Detector

One of the unexpected wins during development: the deduplication layer caught a shard generator producing zero entropy output. The generator had a bug that emitted the same (empty) content across shards, and the content addressed store dutifully collapsed them all to a single hash.

That collapse was the alarm. A model manifest pointing 12 shard slots at one identical hash is either a remarkable coincidence or a broken pipeline. In a filename based system this bug ships silently; the files have different names, so nothing compares them. In UberCode, identical content cannot hide, because identical content is one object.

The general lesson: when your storage layer refuses to store the same bytes twice, any process that accidentally produces duplicate bytes becomes visible immediately. Deduplication is not just a cost optimization, it is an invariant checker.

## What This Means For Operations

For teams running model serving in production, the arithmetic is simple. Restarting a model server or recovering a broken pull costs seconds instead of a full re download. Concretely:

- **Server restarts** against a warm cache are near instant, which makes aggressive rollout and rollback strategies cheap. Restarts stop being an incident multiplier.
- **Spot instance churn** stops being a data transfer problem. A replacement node pulls only the shards its predecessor did not finish.
- **Multi model fleets** share shards across variants automatically, cutting storage and transfer bills without a deduplication service to run.
- **Corrupted transfers** self heal at shard granularity, and corruption cannot persist silently because nothing is trusted without a hash match.

The design shifts integrity, deduplication, and resumability from operational concerns to structural properties. That is the difference between systems you babysit and systems you trust.

## Conclusion

UberCode treats model weights the way content addressed storage treats everything else: as verifiable, deduplicated, cacheable chunks whose identity is their content. The measured result, 1.34 seconds to bring up a 100 megabyte model across 12 fully verified shards, is not a heroic optimization. It is what happens when verification and transport are the same operation and the cache is always correct by construction.

At Tech Guard we think weight delivery should be as boring as package management. Content addressed shards get us there, and they surface pipeline bugs like zero entropy generators along the way. Restart a server, recover a pull, ship a variant: pull what is missing, verify what arrives, ignore what you already have.

---

## Alternate Titles

1. UberCode: 100 Megabyte Models In 1.34 Seconds With Content Addressed Shards
2. Content Addressed Shards Are The Right Way To Ship Model Weights
3. How UberCode Turns Model Weight Delivery Into A Zero Byte Warm Start

## X Hooks

1. Cold bring up of a 100MB model: 1.34 seconds, every shard hash verified. Warm start: zero bytes pulled. Content addressed shards make weight delivery a rounding error. Interrupted download? Resume fetches only what is missing.

2. Our dedup layer caught a shard generator emitting zero entropy output. Identical bytes cannot hide in a content addressed store: they collapse to one hash and the manifest screams. Content addressing is an invariant checker, not just a storage trick.
