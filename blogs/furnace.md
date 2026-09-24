# Furnace: Distributed Training That Survives Getting Killed

Most long training jobs are a bet on nothing going wrong. A machine reboots, an OOM killer fires, a spot instance gets reclaimed, and days of compute evaporate. Furnace is Tech Guard's take on the opposite design: a training stack where being killed is just another event in the schedule, not a disaster. A two rank job was hard killed mid run with SIGKILL, no cleanup, no warning. The supervisor restarted it on a fresh rendezvous port, resumed from the last checkpoint with optimizer state intact, and the job finished. Resume cost was seconds, not hours.

This post walks through how Furnace works, why the hard cases are the ones that matter, and what we learned proving it on a real run.

## The Problem: Kill Minus Nine Is Not a Checkpoint

Checkpointing in most frameworks is an opt in afterthought. You save every N steps if you remember to wire it up, and the save path is chosen for convenience, not recoverability. The failure mode shows up the first time a job gets killed with SIGKILL, which by definition skips every handler, every atexit hook, and every graceful flush you planned.

A checkpoint only counts if it was complete before the kill, not after. That means:

- Atomic writes. The checkpoint file must never exist in a half written state. Furnace writes to a temp file, fsyncs it, then atomically renames it over the previous checkpoint. A reader either sees the old checkpoint or the new one, never a torn file.
- Checkpoint ahead of the loss curve. A rank can die at step 35 with the last checkpoint at step 30. That is fine. Losing a few hundred steps of progress is the cost of doing business; losing the whole job is not.
- Every recovery relevant state in one place: model weights, optimizer moments, learning rate scheduler position, step counter, and the RNG state used for data shuffling.

The last point is the one people forget. If you resume with fresh RNG state, your data order changes and your loss curve is not comparable. If you resume without optimizer state, momentum and Adam statistics reset and the first few hundred steps after resume are garbage. A checkpoint that misses either is a resume that looks like it worked and quietly did not.

## What Furnace Actually Does

Furnace wraps distributed training (torch DDP over gloo in our setup) with a supervisor process that owns the job lifecycle. Workers are separate processes, even for a single rank, because a fault injected in the main process would kill the supervisor along with everything else. The split is deliberate: the supervisor's only job is to notice death and start the next attempt.

The resume path is small and boring, which is the point:

```python
ckpt_path = latest_checkpoint(run_dir)
if ckpt_path:
    state = torch.load(ckpt_path)
    model.load_state_dict(state["model"])
    optimizer.load_state_dict(state["optimizer"])
    scheduler.load_state_dict(state["scheduler"])
    start_step = state["step"]
    set_rng_state(state["rng"])
else:
    start_step = 0
```

The devil is in the details around this snippet:

- **Rendezvous ports are picked fresh per attempt**, random in a range per attempt, so a killed worker holding an old port cannot poison the restart. Pinning a fixed port is a classic way to make the second attempt hang forever.
- **One shot faults are consumed, not replayed.** Our fault injector fires once per attempt. If the supervisor did not mark the fault as consumed, the restart would die at the same step in an infinite loop. A recovery system that loops is worse than one that fails loudly.
- **DataLoader shuffling uses a dedicated generator** seeded from the checkpoint's RNG state, so resumed runs see the same data order as an uninterrupted run at that step.

## The Proof: Two Ranks, Hard Kill, Clean Resume

We do not claim resilience without a real run behind it. The Furnace verification ran a two rank training job with fault injection set to hard kill the whole job at step 35. SIGKILL, the strongest kill available, no chance to clean up.

What happened, from the actual logs:

- The job started from scratch, training normally. Loss descended from 27.05 as expected.
- At step 35, every rank was killed. The supervisor detected the dead workers within seconds.
- The supervisor launched a new attempt on a fresh rendezvous port and resumed from the step 30 checkpoint. Loss after resume started at 21.48, matching the interrupted trajectory rather than restarting from scratch.
- The supervisor reported `attempts=2` and the job ran to its target step.

The resume cost the job five steps of progress and a few seconds of wall clock. An uninterrupted reference run and the interrupted run land on the same loss trajectory. That is the entire product promise in one log file.

We also verified a single rank fault at step 25 with resume at step 20, loss 27.83 dropping to 15.17 after resume, to confirm the design does not depend on world size.

## Why the Supervisor Model Beats In Process Recovery

An in process try/except around the training loop cannot save you from SIGKILL, because the process that holds the handler is the process that dies. Recovery has to live in a process that outlives the failure. That is the core architectural decision in Furnace.

The supervisor keeps three responsibilities:

1. **Health detection.** Watch worker processes, not heartbeats in logs. A dead PID is unambiguous in a way that a stalled heartbeat never is.
2. **Attempt orchestration.** Pick a fresh rendezvous port, launch workers, hand them the run directory. The workers stay stateless about previous attempts.
3. **Bounded retries.** A crash loop is a job that failed in a complicated way. Furnace caps attempts and reports the failure honestly instead of burning GPU hours forever.

This also makes the recovery path testable. Because the supervisor is a separate process with a small interface, we can inject faults deterministically and assert on outcomes. Recovery code that only runs in production, by definition, is code you cannot trust.

## Where Furnace Stops

Honest scope matters as much as the wins:

- Furnace survives process death, not corrupted storage. If the checkpoint file itself is damaged, that is a different failure class. Atomic renames shrink the window to near zero but do not make it zero.
- It is model agnostic but framework specific to PyTorch state dicts today. Adapting to other training stacks means new serialization, same lifecycle.
- It does not do elastic resharding. The world size at resume must match the checkpoint. Changing the number of ranks mid job is a different, harder problem.
- Frequency of checkpointing trades progress loss against throughput. Furnace gives you the mechanism; the interval is a cost decision, not a correctness one.

## Conclusion

Furnace changes the failure model of long running training from all or nothing to pay per step. A job that gets killed loses everything since the last checkpoint and nothing else. The two rank hard kill proof shows the loop working end to end: death detected, fresh rendezvous, checkpoint resumed with optimizer and RNG state, job finished, seconds of overhead.

For teams running fine tuning jobs and multi day training runs on infrastructure they do not fully control, this is the difference between scheduling around machine uptime and simply not caring about it. Furnace is one of fifteen Tech Guard infrastructure projects built and proven with real runs. The pattern generalizes: keep durable state small and atomic, put recovery outside the blast radius, and inject faults until the recovery path is boring.

---

## Alternate Titles

1. Furnace: Training Jobs That Refuse to Die
2. SIGKILL Your Training Job. It Comes Back in Seconds.
3. Furnace Turns Hard Kills Into a Five Step Setback

## X Hooks

1. We SIGKILLed a 2 rank training job mid run. No handlers, no cleanup, nothing survived the kill. The supervisor restarted it on a fresh rendezvous port, resumed from the last checkpoint with optimizer state intact, and finished the job. Cost: 5 steps and a few seconds.
2. Long training jobs should not be a bet on machine uptime. Furnace survives hard kills with checkpointed resume in seconds, not hours. Death detection, fresh rendezvous, atomic checkpoints. Here is how the design works.
