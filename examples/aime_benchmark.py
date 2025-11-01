import argparse
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple

import gepa
from turbo_gepa.adapters.default_adapter import DefaultAdapter, DefaultDataInst
from turbo_gepa.config import Config, adaptive_config

"""
AIME Benchmark - TurboGEPA vs GEPA Performance Comparison

This benchmark optimizes prompts for solving American Invitational Mathematics Examination (AIME)
problems and measures wall-clock speed and throughput.

PERFORMANCE OPTIMIZATIONS APPLIED:
===================================

1. MAXIMUM CONCURRENCY
   - Dynamically calculates max safe concurrency from system file descriptor limits
   - Overrides adaptive_config to use full system capacity
   - Formula: min(fd_limit / 10, 2048) with minimum of 64

2. AGGRESSIVE MUTATION GENERATION
   - max_mutations_per_round: 32+ (high parallelism)
   - mutation_buffer_min: eval_concurrency / 4 (keeps pipeline fed)
   - queue_limit: 2x eval_concurrency (prevents starvation)

3. EFFICIENT ASHA PRUNING
   - Shards tuned via adaptive_config("aggressive")
   - cohort_quantile: 0.5 (top 50% advance)
   - eps_improve: 0.0 (don't over-prune equal quality)

4. CONVERGENCE ACCELERATION
   - enable_rung_convergence: True (auto-promote stagnant candidates)
   - lineage_patience: 2 (force promotion after 2 stagnant children)
   - lineage_min_improve: 1% (threshold for lineage reset)

5. SINGLE ISLAND MODE
   - n_islands: 1 (no inter-island migration overhead for benchmarking)

6. AUTO-STOP ON TARGET QUALITY
   - Stops immediately when target quality reached (no wasted evaluations)

BENCHMARK RESULTS HISTORY:
==========================
TurboGEPA v1: 310.7s @ 83.3% quality (0 evaluations shown - logging bug)
GEPA: 640.3s @ ~70% quality (50 metric calls)

Run with: python examples/aime_benchmark.py --run turbo
          python examples/aime_benchmark.py --run both
"""


def _ensure_fd_limit(min_soft: int = 4096) -> Tuple[bool, Optional[int], Optional[int]]:
    """Raise soft RLIMIT_NOFILE if possible and register restoration."""

    try:
        import resource
    except ImportError:  # pragma: no cover - non-Unix systems
        return False, None, None

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError):
        return False, None, None

    desired = min_soft
    if hard != resource.RLIM_INFINITY:
        desired = min(desired, hard)

    if desired <= soft:
        return False, soft, soft

    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (desired, hard))
    except (OSError, ValueError):
        return False, soft, soft

    import atexit

    def _restore_limit() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
        except (OSError, ValueError):
            pass

    atexit.register(_restore_limit)
    return True, desired, soft


# Parse command line arguments
parser = argparse.ArgumentParser(description="Benchmark GEPA vs TurboGEPA")
parser.add_argument(
    "--run",
    choices=["gepa", "turbo", "both"],
    default="turbo",
    help="Which benchmark to run: gepa, turbo, or both (default: turbo)",
)
args = parser.parse_args()

RUN_GEPA = args.run in ("gepa", "both")
RUN_TURBO = args.run in ("turbo", "both")

limit_changed, new_limit, previous_limit = _ensure_fd_limit()
if limit_changed and new_limit is not None and previous_limit is not None:
    print(f"🔧 Raised open file limit from {previous_limit} to {new_limit}\n")

# ============================================================================
# Load Dataset (shared by both benchmarks)
# ============================================================================

trainset, valset, _ = gepa.examples.aime.init_dataset()

# # Use smaller subset for faster benchmark
BENCHMARK_SIZE = 10  # Very small subset for quick testing
trainset = trainset[:BENCHMARK_SIZE]
valset = valset[: min(BENCHMARK_SIZE, len(valset))]

print(f"📊 Loaded {len(trainset)} training problems (subset for benchmarking)")
print(f"📊 Loaded {len(valset)} validation problems\n")

# ============================================================================
# GEPA (Original) Benchmark
# ============================================================================

gepa_quality = 0.0
gepa_evaluations = 0
gepa_elapsed = 0.0
gepa_prompt = ""
task_lm = "openrouter/openai/gpt-oss-20b:nitro"
reflection_lm = "openrouter/x-ai/grok-4-fast"

if RUN_GEPA:
    print("=" * 80)
    print("GEPA (ORIGINAL) OPTIMIZATION")
    print("=" * 80 + "\n")

    seed_prompt = {
        "system_prompt": "You are a helpful assistant. You are given a question and you need to answer it. The answer should be given at the end of your response in exactly the format '### <final answer>'"
    }

    print("🚀 Starting GEPA optimization (50 metric calls to set target)...\n")

    # Time the GEPA optimization - reasonable budget to establish baseline
    gepa_start = time.time()
    gepa_result = gepa.optimize(
        seed_candidate=seed_prompt,
        trainset=trainset,
        valset=valset,
        task_lm=task_lm,  # Student model (fast, cheap)
        reflection_lm=reflection_lm,
        max_metric_calls=50,  # 50 evaluations to establish baseline quality
        display_progress_bar=True,
        raise_on_exception=False,
    )
    gepa_elapsed = time.time() - gepa_start

    # Extract quality and metrics from GEPA result
    if hasattr(gepa_result, "val_aggregate_scores") and gepa_result.val_aggregate_scores:
        # Get the best score from val_aggregate_scores
        best_idx = gepa_result.best_idx
        gepa_quality = gepa_result.val_aggregate_scores[best_idx]

    gepa_evaluations = 50  # metric calls
    gepa_prompt = gepa_result.best_candidate["system_prompt"]

    print(f"\n✅ GEPA completed in {gepa_elapsed:.1f}s")
    print(f"📊 Best quality: {gepa_quality:.1%}")
    print(f"📊 Total metric calls: {gepa_evaluations}")
    print(f"\n🎯 TARGET: TurboGEPA must reach {gepa_quality:.1%} quality")
    print(f"   We'll measure how long it takes and how many evaluations needed\n")
    print(f"📝 GEPA Optimized Prompt: {gepa_prompt}")


# ============================================================================
# TurboGEPA Benchmark
# ============================================================================

turbo_quality = 0.0
turbo_evaluations = 0
turbo_elapsed = 0.0
turbo_prompt = ""
mutations_generated = 0
mutations_promoted = 0

if RUN_TURBO:
    # Wipe the cache using shutil for safer cross-platform removal
    cache_dir = Path(".turbo_gepa/")
    print(f"🧹 Cache directory check: {cache_dir.resolve()}")
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"   ✅ Cleared existing cache")
    else:
        print(f"   ℹ️  No existing cache to clear")
    print("\n" + "=" * 80)
    print("TURBOGEPA OPTIMIZATION")
    print("=" * 80 + "\n")

    # Convert GEPA dataset to TurboGEPA format (use same data as GEPA)
    quick_limit = min(len(trainset), 10)  # Very small for quick testing
    turbo_dataset = [
        DefaultDataInst(
            input=ex["input"],
            answer=ex["answer"],
            id=f"aime_{i}",
            additional_context=ex.get("additional_context"),
        )
        for i, ex in enumerate(trainset[:quick_limit])
    ]

    print(f"📊 Loaded {len(turbo_dataset)} AIME problems (quick benchmark subset)")

    # Dynamically determine maximum safe concurrency based on system resources
    import resource
    import os

    # Get file descriptor limit
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    cpu_count = os.cpu_count() or 10

    # For async I/O-bound LLM calls, we can go much higher than CPU count
    # Rule: Use min of (soft_limit / 10, 2048) to leave headroom for other processes
    # This ensures we don't exhaust file descriptors while maximizing throughput
    max_safe_concurrency = min(soft_limit // 10, 2048)

    # Ensure minimum of 64 for reasonable throughput
    max_concurrency = max(64, max_safe_concurrency)

    print(f"🖥️  System resources:")
    print(f"   CPU cores: {cpu_count}")
    print(f"   File descriptor limit: {soft_limit:,} (soft), {hard_limit:,} (hard)")
    print(f"   Calculated max safe concurrency: {max_concurrency:,}\n")

    # Create config optimized for MAXIMUM SPEED
    target_quality_val = gepa_quality if RUN_GEPA else 0.70

    # Use simple single-shard config for testing
    config = Config(
        shards=(1.0,),  # Single shard - evaluate on full dataset
        eval_concurrency=64,  # Reasonable concurrency
        max_mutations_per_round=16,
        mutation_buffer_min=8,
        queue_limit=256,
        batch_size=8,
    )

    # Quality settings
    config.target_quality = target_quality_val
    config.eps_improve = 0.0  # Accept equal quality
    config.cohort_quantile = 0.5  # Keep top 50%

    # Create adapter
    adapter = DefaultAdapter(
        dataset=turbo_dataset,
        task_lm=task_lm,
        reflection_lm=reflection_lm,
        config=config,
        auto_config=False,
    )

    seed_turbo = "You are a helpful assistant. You are given a question and you need to answer it. The answer should be given at the end of your response in exactly the format '### <final answer>'"

    print("🚀 Starting TurboGEPA optimization...\n")
    print("=" * 80)
    print("PERFORMANCE CONFIGURATION")
    print("=" * 80)
    print(f"🔥 Concurrency: {config.eval_concurrency:,} parallel evaluations")
    print(f"🧬 Mutations: {config.max_mutations_per_round} per round (buffer min: {config.mutation_buffer_min})")
    print(f"📊 Batch size: {config.batch_size}")
    print(f"📋 Queue limit: {config.queue_limit}")
    print(f"🎯 Shards: {config.shards}")
    print(f"⚡ ASHA quantile: {config.cohort_quantile} (top {int((1-config.cohort_quantile)*100)}% advance)")
    print(f"📈 Convergence: {'Enabled' if config.enable_rung_convergence else 'Disabled'}")
    print("=" * 80 + "\n")

    if RUN_GEPA:
        print(f"🎯 Goal: Match/exceed GEPA's {gepa_quality:.1%} quality as fast as possible")
        print(f"🎯 Auto-stop enabled: Will stop when quality ≥ {gepa_quality:.1%}\n")
    else:
        print(f"🎯 Target quality: {target_quality_val:.1%}")
        print("⏱️  Running with max throughput until target reached\n")

    start_time = time.time()
    turbo_result = adapter.optimize(
        seeds=[seed_turbo],
        enable_auto_stop=True,  # Stop when target quality is reached
        max_rounds=50,  # Plenty of rounds to ensure we can match GEPA quality
        max_evaluations=None,  # No evaluation limit
        display_progress=True,
        optimize_temperature_after_convergence=False,
    )
    turbo_elapsed = time.time() - start_time

    # Extract best result - prefer highest shard, then best quality within that shard
    pareto_entries = turbo_result.get("pareto_entries", []) or []
    full_shard = config.shards[-1]  # Last shard = 1.0 (100% of data)

    if pareto_entries:
        # Group candidates by shard fraction
        by_shard = {}
        for entry in pareto_entries:
            shard = entry.result.shard_fraction or 0.0
            if shard not in by_shard:
                by_shard[shard] = []
            by_shard[shard].append(entry)

        # Find highest shard with evaluations
        highest_shard = max(by_shard.keys())
        highest_shard_entries = by_shard[highest_shard]

        # Get best quality from highest shard
        best_entry = max(
            highest_shard_entries,
            key=lambda e: e.result.objectives.get("quality", 0.0),
        )
        turbo_quality = best_entry.result.objectives.get("quality", 0.0)
        turbo_prompt = best_entry.candidate.text
        turbo_shard = highest_shard

        # Warn if not evaluated on full dataset
        if turbo_shard < full_shard:
            print(
                f"⚠️  Warning: Best quality {turbo_quality:.1%} is from {turbo_shard:.1%} shard (not full {full_shard:.0%} dataset)"
            )
    else:
        turbo_quality = 0.0
        turbo_prompt = seed_turbo
        turbo_shard = 0.0

    # Get evolution stats
    evolution_stats = turbo_result.get("evolution_stats", {}) or {}
    mutations_generated = evolution_stats.get("mutations_generated", 0)
    mutations_promoted = evolution_stats.get("mutations_promoted", 0)
    mutations_requested = evolution_stats.get("mutations_requested", 0)
    mutations_enqueued = evolution_stats.get("mutations_enqueued", 0)
    unique_parents = evolution_stats.get("unique_parents", 0)
    unique_children = evolution_stats.get("unique_children", 0)
    evolution_edges = evolution_stats.get("evolution_edges", 0)
    turbo_evaluations = evolution_stats.get("total_evaluations", 0)

    # Get archive stats
    pareto_size = len(pareto_entries)
    total_candidates = turbo_result.get("total_candidates", pareto_size)

    print(f"\n✅ TurboGEPA completed in {turbo_elapsed:.1f}s")
    print(f"📊 Best quality: {turbo_quality:.1%}")
    print(f"📊 Total evaluations: {turbo_evaluations}")
    print(f"\n📈 Evolution Statistics:")
    print(f"   Seeds: 1")
    print(f"   Unique parents used: {unique_parents}")
    print(f"   Unique children generated: {unique_children}")
    print(f"   Total evolution edges: {evolution_edges}")
    print(f"   Mutations requested: {mutations_requested}")
    print(f"   Mutations generated: {mutations_generated}")
    print(f"   Mutations enqueued: {mutations_enqueued}")
    print(f"   Mutations promoted to archive: {mutations_promoted}")
    print(f"   Pareto frontier size: {pareto_size}")
    print(f"   Total unique candidates: {total_candidates}")
    print(f"\n📝 TurboGEPA Optimized Prompt: {turbo_prompt}")

# ============================================================================
# Benchmark Results Summary
# ============================================================================

if RUN_GEPA or RUN_TURBO:
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)

if RUN_GEPA:
    gepa_throughput = gepa_evaluations / gepa_elapsed if gepa_elapsed > 0 else 0
    print("\n📊 GEPA (Original):")
    print(f"   Time: {gepa_elapsed:.1f}s")
    print(f"   Quality: {gepa_quality:.1%}")
    print(f"   Total evaluations: {gepa_evaluations}")
    print(f"   Throughput: {gepa_throughput:.2f} evals/sec")
    print(f"   Time per evaluation: {gepa_elapsed / gepa_evaluations:.2f}s")

if RUN_TURBO:
    turbo_throughput = turbo_evaluations / turbo_elapsed if turbo_elapsed > 0 else 0
    print("\n⚡ TurboGEPA:")
    print(f"   Time: {turbo_elapsed:.1f}s")
    print(
        f"   Quality: {turbo_quality:.1%} (evaluated on {turbo_shard:.1%} of dataset)"
    )
    print(f"   Total evaluations: {turbo_evaluations}")
    print(f"   Throughput: {turbo_throughput:.2f} evals/sec  🔥")
    print(
        f"   Time per evaluation: {turbo_elapsed / turbo_evaluations if turbo_evaluations else 0:.2f}s"
    )
    print(f"\n   Evolution:")
    print(
        f"   └─ Seeds → {unique_parents} parents → {unique_children} children ({evolution_edges} edges)"
    )
    print(
        f"   └─ Generated {mutations_generated} mutations, {mutations_promoted} promoted to Pareto"
    )
    print(
        f"   └─ Final Pareto size: {pareto_size}, Total candidates: {total_candidates}"
    )

# Comparison (only if both were run)
if RUN_GEPA and RUN_TURBO:
    print("\n" + "=" * 80)
    print("TIME-TO-QUALITY COMPARISON")
    print("=" * 80)
    print(f"\n📊 Both systems optimizing to reach {gepa_quality:.1%} quality:")
    print(f"\n   GEPA:      {gepa_elapsed:.1f}s using {gepa_evaluations} evaluations")
    print(f"   TurboGEPA: {turbo_elapsed:.1f}s using {turbo_evaluations} evaluations")

    speedup = gepa_elapsed / turbo_elapsed if turbo_elapsed > 0 else 0
    eval_efficiency = gepa_evaluations / turbo_evaluations if turbo_evaluations > 0 else 0
    throughput_gain = turbo_throughput / gepa_throughput if gepa_throughput > 0 else 0

    print(f"\n🏆 RESULTS:")
    print(f"   Wall-clock speedup: {speedup:.1f}x faster")
    print(f"   Evaluation efficiency: {eval_efficiency:.1f}x fewer evaluations needed")
    print(f"   Throughput: {throughput_gain:.1f}x more evals/sec ({turbo_throughput:.2f} vs {gepa_throughput:.2f})")

    # Quality comparison
    if gepa_quality > 0 and turbo_quality > 0:
        quality_diff = turbo_quality - gepa_quality
        quality_status = "✅ MATCHED" if abs(quality_diff) < 0.01 else ("✅ EXCEEDED" if quality_diff > 0 else "⚠️  LOWER")
        print(f"\n   Quality: {quality_status}")
        print(f"   - TurboGEPA: {turbo_quality:.1%}")
        print(f"   - GEPA:      {gepa_quality:.1%}")
        print(f"   - Difference: {quality_diff:+.1%}")
    elif turbo_quality > 0:
        print(f"\n   🎯 TurboGEPA quality: {turbo_quality:.1%}")
    elif gepa_quality > 0:
        print(f"\n   🎯 GEPA quality: {gepa_quality:.1%}")

if RUN_GEPA or RUN_TURBO:
    print("\n" + "=" * 80)
    print("BEST PROMPTS")
    print("=" * 80)

if RUN_GEPA:
    print("\n📝 GEPA Best Prompt:")
    print(gepa_prompt)

if RUN_TURBO:
    print("\n⚡ TurboGEPA Best Prompt:")
    print(turbo_prompt)

if RUN_GEPA or RUN_TURBO:
    print("\n" + "=" * 80)
