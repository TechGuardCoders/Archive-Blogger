# Popcorn: How We Made Text Normalization 14.75x Faster Without Changing a Single Byte

Every token your model sees has already been scrubbed. Before tokenization, raw text passes through normalization: unicode folding, whitespace collapsing, control character stripping, quote canonicalization. Nobody celebrates this code. It sits in the cold path of the data pipeline, quietly eating CPU on every ingest job. At Tech Guard we run a private AI lab that ingests web scale text, and when we profiled the pipeline, normalization was the top cost in the preprocessing stage. Popcorn is our teardown of that cost: a CPython C extension that replaced the Python regex chain and delivered a 14.75 times speedup. The part that matters more than the number is how we know the number is real.

## Where the Time Actually Goes

Normalization looks trivial until you count operations. A typical Python chain runs five to ten regex passes per document: NFKC folding via unicodedata, a whitespace collapse, a control character strip, a punctuation map, a quote replacement. Each pass walks the entire string. A 50 kilobyte document gets walked ten times, and each walk allocates a new string.

The Python cost is not the regex engine itself. `re` is implemented in C. The cost is everything around it:

* Per call overhead from Python object dispatch, argument parsing, and pattern cache lookups
* String allocation on every pass, because each regex returns a new str
* Python level glue: list comprehensions, conditionals on match results, `unicodedata.normalize` calls from pure Python
* Repeated scanning, because pass three rediscovers the characters pass one already saw

Individually these are microseconds. At billions of documents they are hours of billable compute.

## What Popcorn Replaces

Popcorn is a single CPython C extension that fuses the whole chain into one pass. Instead of running ten regexes over the string, a single state machine walks each byte once, classifies it, and writes to one preallocated output buffer. Unicode folding uses the same `unicodedata` tables CPython itself uses, called directly in C instead of through a Python call boundary.

The design rules were strict:

* One pass over the input, one output allocation, no intermediate strings
* Classification via a 256 entry lookup table for ASCII, table plus folding logic for multibyte sequences
* No Python objects touched in the hot loop, no `PyUnicode_FromFormat`, no refcount churn per character
* Result built as a `PyUnicode` object with a single resize at the end

The fused pass also enabled a correctness improvement the Python version could not express cheaply: overlapping operations that previously required careful regex ordering now resolve deterministically inside the state machine, because each character is classified exactly once.

## The Byte Exact Gate

A speedup means nothing if the output differs. Popcorn ships with a gate: 400 real corpus samples, spanning scripts, languages, and edge cases we collected from actual ingest failures. The gate runs both implementations on every sample and compares raw bytes. Not similarity scores. Not sampled spot checks. Full byte equality on every sample, every run.

The gate runs in CI on every commit. If the fast path ever diverges from the reference chain, the build fails with the sample index, the offset, and the hex of both outputs. Nobody argues about whether a difference is acceptable. The gate answers it mechanically.

This is the core Tech Guard discipline: speed claims are only real if the output is identical. A benchmark number without an equivalence gate is marketing.

## Three Bugs the Gate Caught

During development, the gate caught three real bugs. Each one passed eyeball inspection and synthetic tests.

* Quote folding off by one class. The C table mapped one obscure quotation variant to the wrong target. It affected roughly one character in ten million, invisible in casual review, caught on sample 187.
* Multi byte boundary handling. A malformed UTF-8 sequence at a buffer edge was silently dropped by the C pass instead of preserved. The Python regex chain kept it. The gate flagged a two byte difference in a mixed language sample.
* Ordering dependency in whitespace collapse. The fused pass collapsed a space adjacent to a control character differently than the sequential regex chain did. Both outputs looked clean. They were not identical.

All three bugs would have shipped in a benchmark driven workflow, because the benchmarks would have looked great and the outputs would have looked plausible. Byte level verification converts "looks right" into "is right."

## Why Byte Exact Verification Scales

The instinct against this level of verification is cost. It is cheap. The gate runs in seconds, the sample set is static and versioned, and comparison is a `memcmp` loop. The expensive part was writing the reference implementation once, and we already had it: the original Python chain is the reference.

The pattern generalizes to any hot path rewrite:

* Freeze the old implementation as the oracle. Do not delete it, version it.
* Capture real inputs, not synthetic ones. Edge cases live in production traffic, not in your imagination.
* Compare at the lowest level available: bytes, not parsed structures, not metrics.
* Gate it in CI so equivalence is enforced, not remembered.

For data security work this discipline doubles as an audit trail. When preprocessing is byte exact, downstream provenance claims hold. You can prove the data your model saw is the data you claim it saw.

## What 14.75x Buys

The measured speedup on our production corpus was 14.75 times end to end for the normalization stage, not microbenchmarks on toy strings. In pipeline terms, normalization dropped from a leading share of preprocessing CPU to a rounding error. Ingest jobs that were normalization bound became parsing bound, which is where the interesting work actually happens.

The takeaway is not that you should write C extensions. It is that you should profile the unglamorous stages first, because they are where the easy large multipliers hide. Text normalization, deduplication hashing, file format decoding: these run before anyone looks at the output, so nobody notices they are slow.

## Conclusion

Popcorn replaced a decade old Python regex chain with a single pass C extension and made text normalization 14.75 times faster. The speedup is only half the story. A 400 sample byte exact gate proved the fast path is indistinguishable from the original, and that gate caught three real bugs along the way. That is the argument for byte level verification in general: correctness is checkable, so check it. At Tech Guard this is the standard we apply to every hot path claim, on our own infrastructure and on every system we build for customers. Speed is only real if the output is identical.

---

## Alternate Titles

* Popcorn: A 14.75x Speedup With Zero Changed Bytes
* The Regex Chain We Replaced and the Gate That Kept It Honest
* Byte Exact or It Did Not Happen: Inside the Popcorn Normalizer

## X Hooks

* We made text normalization 14.75x faster with a CPython C extension. The interesting part is not the speedup. It is the 400 sample byte exact gate that caught three real bugs before they shipped. Speed is only real if the output is identical.

* Nobody profiles the string cleanup before tokenization. We did. One fused C pass replaced ten regex chains, 14.75x faster, and a byte for byte gate proved not one output byte changed. Three bugs the benchmarks never saw. That gate is the whole point.
