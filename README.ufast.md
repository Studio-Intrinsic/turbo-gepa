# uFast-GEPA Quickstart

This fork adds a high-throughput, island-aware optimizer inspired by GEPA. The `src/ufast_gepa` package is self-contained and keeps dependencies to the Python standard library. Use it when you want GEPA-quality prompt evolution with aggressive async orchestration and caching, without extra infrastructure.

## Quick Start

### Single-Island Demo

The simplest way to get started:

```bash
python examples/run_local_demo.py
```

This runs a single-island optimization with a synthetic dataset and logs results to `.ufast_gepa/logs/demo_run.jsonl`.

### Multi-Island Demo

For distributed optimization with migrations:

```bash
python examples/run_multi_island_demo.py
```

This launches 4 islands in parallel with ring topology migrations every 2 rounds.

### Benchmark Analysis

After running either demo, analyze performance KPIs:

```bash
python examples/benchmark_run.py --log-path .ufast_gepa/logs/demo_run.jsonl
```

Or for JSON output:

```bash
python examples/benchmark_run.py --json
```

### Adapter Usage

Want to mirror the classic GEPA default pipeline? Use the built-in adapter:

```python
from ufast_gepa.adapters.default_adapter import DefaultAdapter, DefaultDataInst

dataset = [DefaultDataInst(input=row["input"], answer=row["answer"], id=row["id"]) for row in rows]
adapter = DefaultAdapter(dataset)
result = adapter.optimize(
    seeds=["You are a helpful assistant."],
    max_rounds=3,
    max_evaluations=200,
)
```

`result["pareto"]` gives you the high-quality prompts, and the adapter takes care of the sampler, cache, mutator, and orchestrator wiring.

## Integration Steps

1. **Provide LLM hooks** – implement `task_lm_call` and `reflect_lm_call` in `src/ufast_gepa/user_plugs_in.py`. The file ships with deterministic heuristics for local runs; replace them with calls into your production LLM stack. `task_lm_call` should accept a candidate prompt and example payload, returning metrics like `{"quality": float, "neg_cost": float, "tokens": float}`. `reflect_lm_call` receives failure traces plus the parent prompt and must return mutated prompt strings.

2. **Pick an adapter** – for single-component prompt optimization, use `ufast_gepa.adapters.DefaultAdapter`, which mirrors GEPA’s default adapter and wires the sampler, cache, mutator, and orchestrator automatically. You can still assemble components manually for custom setups.

3. **Create a dataset iterator** – feed `InstanceSampler` the IDs for your evaluation corpus (JSONL works well). Tag difficult cases so the hardness sampler can rebalance future shards. The default adapter accepts payloads with `input`, `answer`, and optional `additional_context` fields.

4. **Instantiate the orchestrator** – wire up `DiskCache`, `AsyncEvaluator`, `Archive`, `InstanceSampler`, and a `Mutator` built with `MutationConfig`, or let the adapter handle this boilerplate. The demo at `examples/run_local_demo.py` shows the minimal wiring and includes a synthetic dataset.

5. **Launch islands** – run one orchestrator per process using `multiprocessing`. Use `islands.spawn_islands` with your orchestrator worker to enable non-blocking migrations in a ring topology.

6. **Wire migrations** – pass the `IslandContext` from your worker into `Orchestrator` so `migration_period` and `migration_k` control how elites circulate.

## Multi-Island Example

Here's a complete multi-island setup:

```python
from ufast_gepa.islands import spawn_islands, IslandContext
from ufast_gepa.orchestrator import Orchestrator
from ufast_gepa.config import Config

def island_worker(island_id: int, context: IslandContext, config: Config):
    # Create island-specific components
    orchestrator = Orchestrator(
        config=config,
        evaluator=...,
        archive=...,
        sampler=...,
        mutator=...,
        cache=...,
        island_context=context,  # Enable migrations
    )

    # Run with different seeds per island for diversity
    seeds = [Candidate(text=f"Island {island_id}: ...")]
    asyncio.run(orchestrator.run(seeds, max_rounds=10))

# Launch 4 islands with ring topology
config = Config(n_islands=4, migration_period=2, migration_k=3)
worker = lambda ctx: island_worker(get_island_id(), ctx, config)
processes = spawn_islands(config.n_islands, worker)

for proc in processes:
    proc.join()
```

The orchestrator automatically:
- Sends top-K elites to the next island every `migration_period` rounds
- Receives elites from the previous island
- Deduplicates incoming candidates by fingerprint
- Inserts valid migrants into the local archive

## Config Knobs (`ufast_gepa/config.py`)

### Concurrency & Parallelism
- `eval_concurrency` (default: 64) – Max concurrent evaluations per island
- `n_islands` (default: 4) – Number of parallel optimization processes

### Successive Halving
- `shards` (default: [0.05, 0.2, 1.0]) – Shard size rungs as fractions of dataset
- `eps_improve` (default: 0.01) – Minimum improvement to promote
- `cohort_quantile` (default: 0.6) – Top 40% promote to next shard

### Quality-Diversity Archive
- `qd_bins_length` (default: 8) – Bins for prompt length dimension
- `qd_bins_bullets` (default: 6) – Bins for bullet count dimension
- `qd_flags` (default: ["cot", "format", "fewshot"]) – Feature flags for QD grid

### Mutation & Evolution
- `amortized_rate` (default: 0.8) – Probability of rule-based edits vs reflection
- `reflection_batch_size` (default: 6) – Max traces per reflection call
- `max_mutations_per_round` (default: 16) – Cap on mutations generated per round

### Merging & Compression
- `merge_period` (default: 3) – Merge candidates every N rounds
- `merge_uplift_min` (default: 0.01) – Minimum improvement to accept merge
- `max_tokens` (default: 2048) – Token budget for candidates
- `prune_delta` (default: 0.005) – Quality tolerance for compression
- `compression_shard_fraction` (default: 0.2) – Shard size for compression validation

### Island Migration
- `migration_period` (default: 2) – Migrate elites every N rounds
- `migration_k` (default: 3) – Number of elites to send per migration

### Logging & Monitoring
- `cache_path` (default: ".ufast_gepa/cache") – Disk cache directory
- `log_path` (default: ".ufast_gepa/logs") – JSONL log directory
- `log_summary_interval` (default: 10) – Emit summary every N rounds

### Other
- `batch_size` (default: 8) – Candidates evaluated per round
- `queue_limit` (default: 128) – Max queue depth for pending candidates
- `promote_objective` (default: "quality") – Objective for promotion decisions
- `compression_objective` (default: "quality") – Objective to preserve during compression

Defaults live in code so you can override quickly via keyword args or by cloning `Config`.

## Logging & Outputs

### Event Logs

Structured JSONL logs land in `.ufast_gepa/logs/` (see `logging_utils.py`). Key events include:

- `eval_start` / `eval_done` – Evaluation lifecycle
- `promote` – Candidates promoted to next shard
- `archive_update` – Archive insertions with objectives
- `mutation_proposed` / `mutation_accepted` – Mutation lifecycle
- `merge_proposed` / `merge_accepted` / `merge_rejected` – Merge lifecycle
- `compression_applied` – Token compression results
- `migrate_out` / `migrate_in` – Island migrations
- `summary` – Periodic aggregated metrics

### Summary Metrics

Every `log_summary_interval` rounds, the orchestrator emits a summary with:
- **Queue depth** – Number of pending candidates
- **Pareto size** – Current Pareto frontier size
- **Evaluations** – Total evaluations run
- **Hardness size** – Number of hard examples tracked

With `SummaryLogger` (optional), you also get:
- **Cache hit rate** – Percentage of cache hits
- **Prune rate** – Percentage pruned at shard 0
- **Latency percentiles** – P50, P95 eval times
- **Objectives histogram** – Min/max/mean/median per objective

### Outputs

After a successful run you can inspect:

- `archive.pareto_candidates()` – Quality/token Pareto frontier
- `archive.sample_qd(k)` – Diversity-focused elites from QD grid
- `.ufast_gepa/cache/` – Cached evaluation results (persistent across runs)
- `.ufast_gepa/logs/` – JSONL event logs for analysis

## Performance KPIs

The implementation targets these KPIs from the project plan:

| KPI | Target | How to Measure |
|-----|--------|----------------|
| **Prune rate at shard-1** | ≥60% | Analyze `promote` events vs shard-0 evaluations |
| **Cache hit rate** | ≥20% after warm-up | Check `summary` events or final metrics |
| **Pareto hypervolume** | Increasing | Track Pareto frontier quality over rounds |
| **Compressed variants** | ≥1 | Count `compression_applied` events |
| **Speedup vs serial** | >10× | Compare wall-clock with baseline (requires real LLM) |

Use the benchmark analyzer to validate:

```bash
python examples/benchmark_run.py
```

Example output:
```
======================================================================
uFast-GEPA Benchmark Report
======================================================================

📊 Timing Metrics
  Total runtime: 12.3s
  Avg eval latency: 45.2ms
  P50 eval latency: 38.1ms
  P95 eval latency: 89.3ms

💾 Cache Metrics
  Hit rate: 28.4%
  Hits: 142, Misses: 358

📈 Archive Metrics
  Pareto size: 5
  QD grid size: 12

✨ Quality Metrics
  Initial quality: 0.452
  Final quality: 0.687
  Improvement: +0.235

======================================================================
KPI Validation
======================================================================
  ✓ Prune rate at shard 0: 64.2%
  ✓ Cache hit rate: 28.4%
  ✓ Pareto size: 5
  ✓ QD grid size: 12
  ✓ Quality improvement: 0.452 → 0.687 (Δ=+0.235)
  ✓ Compressed variants: 3
======================================================================
```

## Testing

Unit coverage for the new stack sits in `tests/ufast_gepa`. The suite only requires `pytest`:

```bash
pip install pytest
pytest tests/ufast_gepa -v
```

End-to-end test with KPI validation:

```bash
pytest tests/ufast_gepa/test_end_to_end.py -v
```

The tests avoid third-party async helpers so they execute cleanly in constrained environments.

### Test Coverage

- `test_interfaces.py` – Data contracts
- `test_cache.py` – Disk cache idempotency
- `test_scheduler.py` – ASHA promotion/pruning
- `test_archive.py` – Pareto dominance + QD grid
- `test_mutator.py` – Edit filters and deduplication
- `test_token_controller.py` – Compression logic
- `test_orchestrator.py` – Integration test
- `test_end_to_end.py` – **Comprehensive KPI validation**

## Definition of Done

The definition of done (Section 13 of the project plan) is encoded in the orchestrator loop and validated by tests:

- ✅ Local run completes on example dataset
- ✅ Non-empty Pareto set and QD grid produced
- ✅ At least one candidate reaches full shard
- ✅ Compressed variant retained on Pareto
- ✅ Logs show pruning, migrations, cache hits
- ✅ Engineer can swap LLM calls without changing internals

Swap in your task/reflection calls, run `examples/run_local_demo.py`, then scale out to multiple islands for production workloads.

## Architecture Overview

```
Multi-Island Topology (Ring)
┌─────────────┐     ┌─────────────┐
│  Island 0   │────▶│  Island 1   │
└─────────────┘     └─────────────┘
       ▲                   │
       │                   ▼
┌─────────────┐     ┌─────────────┐
│  Island 3   │◀────│  Island 2   │
└─────────────┘     └─────────────┘

Per-Island Components
┌────────────────────────────────────────┐
│           Orchestrator                 │
│  ┌──────────────────────────────────┐  │
│  │  Selection → Race → Update       │  │
│  │  Mutation → Merge → Migration    │  │
│  └──────────────────────────────────┘  │
├────────────────────────────────────────┤
│  Archive (Pareto + QD Grid)            │
│  Scheduler (ASHA Successive Halving)   │
│  Mutator (Rule + Reflection)           │
│  Evaluator (Async + Cache)             │
│  Sampler (Coreset + Hardness)          │
│  Token Controller (Compression)        │
└────────────────────────────────────────┘
```

## Next Steps

1. **Plug in real LLMs** – Replace `fake_task_runner` with actual API calls (OpenAI, Anthropic, etc.)
2. **Add your dataset** – Load your evaluation examples instead of synthetic data
3. **Tune config** – Adjust concurrency, shards, and mutation rates for your workload
4. **Scale to production** – Launch multi-island runs for large-scale optimization
5. **Monitor KPIs** – Use benchmark analyzer to track performance over time

For advanced usage and integration patterns, see `examples/run_multi_island_demo.py` and the test suite.
