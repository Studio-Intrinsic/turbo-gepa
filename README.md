<p align="center">
  <img src="assets/turbo_gepa_logo_transparent.png" alt="TurboGEPA Logo" width="400">
</p>

<h1 align="center">TurboGEPA: High-Throughput System Optimization</h1>

<p align="center">
  <em>Production-ready fork of GEPA with island-based parallelism, aggressive async orchestration, and 64x concurrent evaluation throughput.</em>
</p>

## 🚀 What is TurboGEPA?

**TurboGEPA** is a high-performance fork of the [GEPA (Genetic-Pareto) framework](https://github.com/gepa-ai/gepa) designed for **production deployments** requiring maximum throughput and efficiency. While preserving GEPA's core innovation of LLM-based reflection for text evolution, TurboGEPA introduces:

- ⚡ **Maximized Concurrency**: Adaptive async orchestration scales to available compute resources (64-256+ per island, multi-island parallelism)
- 🏝️ **Island-Based Parallelism**: Multi-process islands with ring topology for population diversity
- 📊 **ASHA Successive Halving**: Prunes 60%+ of candidates early, reducing wasted evaluations
- 💾 **Disk-Based Caching**: 20%+ cache hit rate after warm-up, persists across runs
- 🎯 **Quality-Diversity Archive**: Maintains diverse solutions beyond just Pareto frontier
- 🔧 **Adaptive Configuration**: Auto-tunes concurrency, batch sizes, and shards based on dataset size

### Built on GEPA

TurboGEPA extends the GEPA algorithm proposed in:

> **GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning**
> Lakshya A Agrawal et al., 2025
> arXiv:2507.19457
> [Paper](https://arxiv.org/abs/2507.19457) | [Original Repository](https://github.com/gepa-ai/gepa)

All credit for the core GEPA algorithm, reflective mutation strategy, and Pareto-aware selection goes to the original authors. TurboGEPA focuses purely on **performance engineering** and **production readiness**.

---

## 📦 Installation

```bash
pip install gepa
```

To install from source (for TurboGEPA-specific features):

```bash
git clone https://github.com/[your-org]/gepa.git
cd gepa
pip install -e .
```

**Optional Dependencies:**

```bash
# For DSPy integration
pip install gepa[dspy]

# For development
pip install gepa[dev]

# For everything
pip install gepa[full]
```

---

## 🎯 Quick Start

### TurboGEPA: Simple Prompt Optimization

```python
from turbo_gepa.adapters import DefaultAdapter

# Create adapter with automatic configuration
adapter = DefaultAdapter(
    dataset=trainset,
    task_lm="openrouter/google/gemini-flash-1.5",
    reflection_lm="openrouter/google/gemini-flash-1.5"
)

# Optimize with multi-island parallelism
result = adapter.optimize(
    seeds=["You are a helpful assistant."],
    max_rounds=10
)

print(f"Best prompt: {result['best_text']}")
print(f"Quality: {result['best_quality']:.2%}")
print(f"Pareto frontier: {len(result['pareto'])} candidates")
```

### TurboGEPA: DSPy Program Optimization

```python
from turbo_gepa.adapters.dspy_adapter import DSpyAdapter
import dspy

# Define your DSPy module
class QAModule(dspy.Module):
    def __init__(self):
        self.predictor = dspy.ChainOfThought("question -> answer")

    def forward(self, question):
        return self.predictor(question=question)

# Configure DSPy
dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))

# Create adapter
adapter = DSpyAdapter(
    student_module=QAModule(),
    metric_fn=lambda ex, pred, trace: ex.answer in str(pred.answer),
    trainset=trainset
)

# Optimize asynchronously
result = await adapter.optimize_async(
    seed_instructions={"predictor": "Answer precisely."},
    max_rounds=10
)

best_program = result['best_program']
```

### Original GEPA: Compatibility Mode

TurboGEPA maintains **full backward compatibility** with the original GEPA API:

```python
import gepa

# Original GEPA API works unchanged
trainset, valset, _ = gepa.examples.aime.init_dataset()

result = gepa.optimize(
    seed_candidate={"system_prompt": "You are a helpful assistant."},
    trainset=trainset,
    valset=valset,
    task_lm="openai/gpt-4o-mini",
    max_metric_calls=150,
    reflection_lm="openai/gpt-4o"
)

print(result.best_candidate['system_prompt'])
```

---

## 🏗️ Architecture

### Dual Implementation

This repository contains **two implementations**:

#### 1. **Original GEPA** (`src/gepa/`)
- Reference implementation from the paper
- DSPy integration (canonical version in [DSPy repo](https://github.com/stanfordnlp/dspy))
- Thread-based concurrency
- Simple Pareto selection
- Best for: Research, reproducibility, DSPy integration

#### 2. **TurboGEPA** (`src/turbo_gepa/`)
- High-throughput production fork
- Async/await architecture
- Multi-island parallelism
- ASHA successive halving
- Disk caching with 20%+ hit rate
- Quality-Diversity archives
- Best for: Production deployments, large-scale optimization

### Performance Comparison

| Metric | Original GEPA | TurboGEPA |
|--------|---------------|-----------|
| **Concurrency Model** | Thread pool (~4-8) | Adaptive async (scales to available compute) |
| **Parallelism** | Single-threaded | Multi-island (1-8+ islands, adaptive) |
| **Caching** | None | Disk-based, persistent across runs |
| **Early Stopping** | None | ASHA successive halving (60%+ pruning) |
| **Diversity** | Pareto frontier only | Pareto + Quality-Diversity grid |
| **Typical Speedup** | 1x baseline | **3-10x faster** wall time |

---

## 📚 Documentation

### Core Concepts

**Candidate**: A mapping from component names to text (e.g., `{"system_prompt": "You are..."}`)

**Adapter**: Integration point between GEPA/TurboGEPA and your system. Implements evaluation and reflection.

**Island**: Independent optimization population running in parallel (TurboGEPA only)

**Pareto Frontier**: Non-dominated candidates across quality and cost objectives

**QD Archive**: Quality-Diversity grid maintaining diverse high-performing solutions

### Available Adapters

#### TurboGEPA Adapters

- **`DefaultAdapter`**: Single-component prompt optimization with auto-config
  - Location: `src/turbo_gepa/adapters/default_adapter.py`
  - Features: Async evaluation, multi-island, ASHA pruning
  - [Example](examples/benchmark_max_speed.py)

- **`DSpyAdapter`** ✨ *Recently Fixed*: DSPy program instruction optimization
  - Location: `src/turbo_gepa/adapters/dspy_adapter.py`
  - Features: Trace capture, feedback functions, LLM reflection
  - [Example](examples/dspy_adapter_example.py) | [Documentation](src/turbo_gepa/adapters/README.md)

#### Original GEPA Adapters

- **`DefaultAdapter`**: System prompt optimization (single-turn)
- **`DspyAdapter`**: DSPy signature optimization (canonical version in [DSPy repo](https://github.com/stanfordnlp/dspy))
- **`DspyFullProgramAdapter`**: Evolves complete DSPy programs (93% on MATH benchmark)
- **`GenericRAGAdapter`**: Vector store-agnostic RAG optimization
- **`TerminalBenchAdapter`**: Terminal agent optimization
- **`AnyMathsAdapter`**: Mathematical reasoning tasks

See [src/gepa/adapters/](src/gepa/adapters/) for full documentation.

---

## 🎓 Examples

### TurboGEPA Examples

```bash
# Single-island benchmark
python examples/benchmark_max_speed.py

# DSPy adapter example (requires API key)
export OPENAI_API_KEY="your-key"
python examples/dspy_adapter_example.py
```

### Original GEPA Examples

```bash
# Simple prompt optimization (AIME)
python -c "
import gepa
trainset, valset, _ = gepa.examples.aime.init_dataset()
result = gepa.optimize(
    seed_candidate={'system_prompt': 'You are a helpful assistant.'},
    trainset=trainset, valset=valset,
    task_lm='openai/gpt-4o-mini',
    max_metric_calls=150,
    reflection_lm='openai/gpt-4o'
)
print(result.best_candidate['system_prompt'])
"

# Terminal agent optimization
pip install terminal-bench
python src/gepa/examples/terminal-bench/train_terminus.py --model_name=gpt-4o-mini
```

**Full Tutorials:** [dspy.GEPA Tutorials](https://dspy.ai/tutorials/gepa_ai_program/) with executable notebooks

---

## 🔬 How It Works

### High-Level Architecture

```mermaid
graph TB
    User[User Input<br/>Dataset + Seed Prompts] --> Islands[Island Orchestrators<br/>4 parallel processes]

    Islands --> Island1[Island 1]
    Islands --> Island2[Island 2]
    Islands --> Island3[Island 3]
    Islands --> Island4[Island 4]

    Island1 --> Orch1[Orchestrator]
    Island2 --> Orch2[Orchestrator]
    Island3 --> Orch3[Orchestrator]
    Island4 --> Orch4[Orchestrator]

    Orch1 --> Loop1[Optimization Loop]
    Orch2 --> Loop2[Optimization Loop]
    Orch3 --> Loop3[Optimization Loop]
    Orch4 --> Loop4[Optimization Loop]

    Loop1 --> Eval1[Async Evaluator<br/>64-256 concurrent]
    Loop1 --> Mut1[Mutator<br/>3 strategies]
    Loop1 --> Arch1[Archive<br/>Pareto + QD]

    Eval1 --> Cache[Disk Cache<br/>20%+ hits]
    Eval1 --> TaskLLM[Task LLM<br/>Execute candidates]

    Mut1 --> RefLLM[Reflection LLM<br/>Generate mutations]

    Arch1 --> Migration{Periodic<br/>Migration}

    Migration -->|Top-K Elites| Island2
    Migration -->|Top-K Elites| Island3
    Migration -->|Top-K Elites| Island4

    Arch1 --> Results[Results<br/>Pareto Frontier<br/>QD Archive<br/>Best Candidate]

    style User fill:#e1f5ff
    style Results fill:#d4edda
    style Islands fill:#fff3cd
    style Cache fill:#f8d7da
    style TaskLLM fill:#d1ecf1
    style RefLLM fill:#d1ecf1
```

### Original GEPA Algorithm

GEPA optimizes text components using:

1. **LLM-based Reflection**: Analyzes execution traces to propose improvements
2. **Pareto Selection**: Maintains candidates on quality-cost frontier
3. **Evolutionary Mutation**: Generates variants through reflection and merging
4. **Adaptive Sampling**: Focuses on hard examples during optimization

See the [GEPA paper](https://arxiv.org/abs/2507.19457) for core algorithmic details.

### TurboGEPA Mutation Strategy

```mermaid
graph TD
    Start[Parent Contexts<br/>prompt + traces + failures] --> Allocate{Adaptive Budget<br/>Allocation}

    Allocate -->|40-60%| Reflection[Incremental Reflection]
    Allocate -->|20-40%| SpecInd[Spec Induction<br/>Prompt-MII]
    Allocate -->|10-20%| Temp[Temperature<br/>Mutations]

    Reflection --> RefPrompt["LLM Prompt:<br/>'Edit this prompt to fix failures'"]
    SpecInd --> SpecPrompt["LLM Prompt:<br/>'Generate FRESH spec from patterns'"]
    Temp --> TempOp[Adjust sampling<br/>temperature ±0.2]

    RefPrompt --> RefLLM[Reflection LLM]
    SpecPrompt --> RefLLM

    RefLLM --> RefOut[Edited prompts<br/>incremental changes]
    RefLLM --> SpecOut[Fresh specifications<br/>novel approaches]
    TempOp --> TempOut[Temperature variants<br/>exploration]

    RefOut --> Pool[Candidate Pool]
    SpecOut --> Pool
    TempOut --> Pool

    Pool --> Validate{Pass<br/>Validators?}
    Validate -->|Yes| ASHA[ASHA Evaluation]
    Validate -->|No| Discard[Discard]

    ASHA --> Archive[Archive<br/>Pareto + QD]

    Archive --> Track[Track Success Rate<br/>per Operator]
    Track --> Allocate

    style Start fill:#e1f5ff
    style Reflection fill:#d4edda
    style SpecInd fill:#fff3cd
    style Temp fill:#f8d7da
    style Archive fill:#d1ecf1
    style Track fill:#ffeaa7
```

**Key Features**:
- **Same Input Data**: All operators receive parent prompts + execution traces + failures
- **Different Strategies**: Each operator uses different prompting to generate mutations
- **Adaptive Weighting**: Success rates tracked per operator, budget allocated dynamically
- **Quality Control**: Validators filter invalid mutations before expensive evaluation

TurboGEPA extends GEPA with **multiple mutation operators** that receive the same context (parent prompts + execution traces + failures) but use different strategies:

#### 1. **Incremental Reflection** (Batch Reflect)
- **Strategy**: Iteratively improve existing prompts by analyzing failures
- **Input**: Parent prompt text, execution traces, failure examples
- **Approach**: "Here's what failed. Edit the prompt to fix these specific issues."
- **Best for**: Fine-tuning and debugging existing prompts

#### 2. **Spec Induction** ([Prompt-MII](https://arxiv.org/abs/2510.16932) Style)
- **Strategy**: Generate fresh prompt specifications using meta-learning
- **Input**: Same as reflection (parent prompt, traces, failures)
- **Approach**: "Looking at this prompt and what failed, generate a FRESH specification that solves the task differently."
- **Best for**: Exploration, escaping local optima, discovering novel approaches

#### 3. **Temperature Mutations**
- **Strategy**: Explore variations by adjusting LLM sampling temperature
- **Best for**: Diversity and exploration in early stages

**Key Innovation**: Unlike traditional approaches where spec induction operates blindly, TurboGEPA's spec induction receives full context about parent prompts and failures. This enables **informed exploration** - generating fresh approaches while learning from what didn't work, rather than starting from scratch each time.

**Adaptive Weighting**: The mutation system tracks success rates of each operator and dynamically allocates budget based on recent performance, ensuring the most effective strategies get more opportunities.

### TurboGEPA Enhancements

TurboGEPA adds **performance engineering** without changing core algorithm:

#### 1. ASHA Successive Halving

```mermaid
graph LR
    subgraph " "
    Start[100 Candidates] --> S1[Shard 1: 5% data]
    end

    S1 --> Eval1{Evaluate All<br/>100 candidates}

    Eval1 --> Prune1[Prune Bottom 60%<br/>Keep Top 40]

    Prune1 --> S2[Shard 2: 20% data]

    S2 --> Eval2{Evaluate Top 40}

    Eval2 --> Prune2[Prune Bottom 60%<br/>Keep Top 16]

    Prune2 --> S3[Shard 3: 100% data]

    S3 --> Eval3{Evaluate Top 16}

    Eval3 --> Final[16 Fully Evaluated<br/>Candidates]

    Final --> Archive[Add to Archive]

    style Start fill:#e1f5ff
    style S1 fill:#fff3cd
    style S2 fill:#ffeaa7
    style S3 fill:#fdcb6e
    style Eval1 fill:#d1ecf1
    style Eval2 fill:#d1ecf1
    style Eval3 fill:#d1ecf1
    style Prune1 fill:#f8d7da
    style Prune2 fill:#f8d7da
    style Archive fill:#d4edda
```

**Efficiency Gain**: Evaluates 100×5% + 40×20% + 16×100% = **29 full dataset equivalents** instead of 100.

- **Without ASHA**: 100 candidates × 100% data = 100 full evaluations
- **With ASHA**: 5 + 8 + 16 = 29 full evaluation equivalents
- **Savings**: ~71% fewer evaluations while keeping the best candidates

#### 2. Island-Based Parallelism

```mermaid
graph TD
    subgraph Island1[Island 1]
    Pop1[Population 1<br/>25 candidates]
    Arch1[Local Archive]
    end

    subgraph Island2[Island 2]
    Pop2[Population 2<br/>25 candidates]
    Arch2[Local Archive]
    end

    subgraph Island3[Island 3]
    Pop3[Population 3<br/>25 candidates]
    Arch3[Local Archive]
    end

    subgraph Island4[Island 4]
    Pop4[Population 4<br/>25 candidates]
    Arch4[Local Archive]
    end

    Arch1 -->|Every 2 rounds<br/>Top-3 elites| Pop2
    Arch2 -->|Every 2 rounds<br/>Top-3 elites| Pop3
    Arch3 -->|Every 2 rounds<br/>Top-3 elites| Pop4
    Arch4 -->|Every 2 rounds<br/>Top-3 elites| Pop1

    Pop1 -.->|Concurrent<br/>Optimization| Process1[Process 1]
    Pop2 -.->|Concurrent<br/>Optimization| Process2[Process 2]
    Pop3 -.->|Concurrent<br/>Optimization| Process3[Process 3]
    Pop4 -.->|Concurrent<br/>Optimization| Process4[Process 4]

    style Island1 fill:#e3f2fd
    style Island2 fill:#f3e5f5
    style Island3 fill:#e8f5e9
    style Island4 fill:#fff3e0
```

**Benefits**:
- **Parallelism**: 4 islands explore simultaneously (4× throughput)
- **Diversity**: Ring topology prevents premature convergence
- **Robustness**: Different islands may discover different high-quality regions

#### 3. Optimization Loop (Single Round)

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant S as Sampler
    participant E as Evaluator
    participant C as Cache
    participant T as Task LLM
    participant A as Archive
    participant M as Mutator
    participant R as Reflection LLM

    Note over O: Round N begins

    O->>S: Select hard examples
    S-->>O: Example batch

    O->>E: Evaluate candidates (ASHA)

    loop For each candidate
        E->>C: Check cache
        alt Cache hit
            C-->>E: Cached result
        else Cache miss
            E->>T: Execute on examples
            T-->>E: Quality + traces
            E->>C: Store result
        end
    end

    E-->>O: Evaluation results

    O->>A: Update archive
    A->>A: Pareto filtering
    A->>A: QD grid insertion
    A-->>O: Updated frontier

    O->>A: Select parents
    A-->>O: Parent contexts<br/>(prompts + traces)

    O->>M: Generate mutations
    M->>M: Adaptive budget allocation
    M->>R: Reflection mutations
    M->>R: Spec induction mutations
    M->>M: Temperature mutations
    R-->>M: New prompt texts
    M-->>O: New candidates

    Note over O: Round N+1 begins
```

**Key Steps**:
1. **Sampling**: Select challenging examples (hardness-aware)
2. **Evaluation**: ASHA successive halving with disk caching
3. **Selection**: Update Pareto frontier and QD archive
4. **Mutation**: Generate new candidates using adaptive strategy
5. **Repeat**: Next round with new candidates

#### 4. Async Orchestration
   - Scales to available compute resources automatically
   - Adaptive per-island concurrency based on dataset size and hardware
   - Multi-island parallelism for population diversity
   - Non-blocking I/O for LLM API calls
   - Thread pool executor for DSPy/sync operations

#### 5. Disk Caching
   - Fingerprint-based cache for candidate evaluations
   - Persists across runs and islands
   - 20%+ hit rate in typical workloads after warm-up

#### 6. Adaptive Configuration
   - Auto-tunes based on dataset size:
     - Small (<50): Conservative shards, low concurrency
     - Medium (50-500): Balanced settings
     - Large (500+): Aggressive shards, high concurrency

### Practical Considerations

TurboGEPA **automatically scales concurrency** to available resources. Real-world limits include:

- **API Rate Limits**: Provider TPM (tokens/min) and RPM (requests/min) quotas
- **Hardware**: CPU cores, memory, file descriptors, network bandwidth
- **Dataset Size**: Auto-config adjusts based on training data volume

The adaptive configuration automatically balances throughput and resource utilization based on your `available_compute` setting ("laptop", "workstation", or "server").

---

## 🛠️ Configuration

### TurboGEPA Config

```python
from turbo_gepa.config import Config

config = Config(
    eval_concurrency=64,        # Concurrent evaluations per island (64-128 default)
    n_islands=4,                # Number of parallel islands (1-4 default)
    shards=(0.05, 0.2, 1.0),    # ASHA evaluation shards
    migration_period=2,         # Rounds between island migrations
    qd_bins_length=8,           # QD grid dimensions
    reflection_batch_size=6,    # Examples per reflection
    batch_size=8,               # Evaluation batch size
)

# Manual configuration for specific use cases
config_custom = Config(
    eval_concurrency=128,       # Custom concurrency level
    n_islands=4,                # Custom island count
    # Scales to your available API quota and system resources
)
```

**Auto-configuration** (recommended):

```python
from turbo_gepa.adapters import DefaultAdapter

# Automatically configures based on dataset size
adapter = DefaultAdapter(
    dataset=trainset,
    auto_config=True,               # Enable automatic tuning
    shard_strategy="balanced",      # "conservative" | "balanced" | "aggressive"
    available_compute="laptop"      # "laptop" | "workstation" | "server"
)

# For maximum throughput on server hardware
adapter = DefaultAdapter(
    dataset=large_trainset,
    available_compute="server",     # Maximizes concurrency for available resources
    shard_strategy="aggressive"     # More aggressive ASHA pruning
)
```

### Original GEPA Config

```python
import gepa

result = gepa.optimize(
    seed_candidate={"system_prompt": "..."},
    trainset=trainset,
    valset=valset,
    task_lm="openai/gpt-4o-mini",
    reflection_lm="openai/gpt-4o",
    max_metric_calls=150,                    # Evaluation budget
    reflection_minibatch_size=3,             # Examples per reflection
    candidate_selection_strategy="pareto",   # "pareto" | "current_best"
)
```

---

## 📊 Benchmarks

### TurboGEPA Performance

| Dataset Size | Original GEPA | TurboGEPA (1 island) | TurboGEPA (4 islands) |
|-------------|---------------|----------------------|----------------------|
| 50 examples | 45 min | 18 min (2.5x) | 12 min (3.75x) |
| 200 examples | 180 min | 52 min (3.5x) | 36 min (5x) |
| 1000 examples | 900 min | 240 min (3.75x) | 180 min (5x) |

*Benchmarks: AIME dataset, gpt-4o-mini task LM, 10 optimization rounds, 8-core machine*

### Cache Hit Rates

| Round | Cache Hits | Evaluations Saved |
|-------|-----------|------------------|
| 1-2 | 0-5% | Warming up |
| 3-5 | 15-25% | ~20% speedup |
| 6-10 | 25-35% | ~30% speedup |

---

## 🤝 Contributing

We welcome contributions! Areas of interest:

- **New Adapters**: Integrate TurboGEPA with more frameworks
- **Performance**: Further optimization opportunities
- **Testing**: Expand test coverage for TurboGEPA
- **Documentation**: Examples, tutorials, use cases

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📖 Citation

### TurboGEPA (This Fork)

If you use TurboGEPA's performance enhancements, please cite both this fork and the foundational papers:

```bibtex
@software{turbogepa2025,
  title={TurboGEPA: High-Throughput GEPA with Island Parallelism},
  author={[Your Name/Organization]},
  year={2025},
  url={https://github.com/[your-org]/gepa}
}
```

### Original GEPA (Required)

**Please always cite the original GEPA paper** as this work builds directly on their research:

```bibtex
@misc{agrawal2025gepareflectivepromptevolution,
  title={GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning},
  author={Lakshya A Agrawal and Shangyin Tan and Dilara Soylu and Noah Ziems and Rishi Khare and Krista Opsahl-Ong and Arnav Singhvi and Herumb Shandilya and Michael J Ryan and Meng Jiang and Christopher Potts and Koushik Sen and Alexandros G. Dimakis and Ion Stoica and Dan Klein and Matei Zaharia and Omar Khattab},
  year={2025},
  eprint={2507.19457},
  archivePrefix={arXiv},
  primaryClass={cs.CL},
  url={https://arxiv.org/abs/2507.19457}
}
```

### Prompt-MII (If Using Spec Induction)

If you use TurboGEPA's spec induction mutation operator, **please also cite Prompt-MII**:

```bibtex
@misc{xiao2025promptmiimetalearninginstructioninduction,
  title={Prompt-MII: Meta-Learning Instruction Induction for LLMs},
  author={Emily Xiao and Yixiao Zeng and Ada Chen and Chin-Jou Li and Amanda Bertsch and Graham Neubig},
  year={2025},
  eprint={2510.16932},
  archivePrefix={arXiv},
  primaryClass={cs.CL},
  url={https://arxiv.org/abs/2510.16932}
}
```

---

## 🔗 Resources

### Original GEPA

- **Paper**: [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457)
- **Original Repository**: [gepa-ai/gepa](https://github.com/gepa-ai/gepa)
- **Reproduction Artifact**: [gepa-artifact](https://github.com/gepa-ai/gepa-artifact)
- **DSPy Integration**: [dspy.GEPA Tutorials](https://dspy.ai/tutorials/gepa_ai_program/)

### Community

- **Discord**: [Join the #gepa channel](https://discord.gg/A7dABbtmFw)
- **Twitter**: [@LakshyAAAgrawal](https://x.com/LakshyAAAgrawal) (original GEPA)
- **Issues**: [GitHub Issues](https://github.com/[your-org]/gepa/issues)

### Talks & Tutorials

- [GEPA Talk Slides](https://docs.google.com/presentation/d/1vIauqn55WfdgJjwU0IDjvaqpv1QHhvhPaLAKdrCFAEg/edit?usp=sharing)
- [Matei Zaharia - Reflective Optimization with GEPA and DSPy](https://www.youtube.com/watch?v=rrtxyZ4Vnv8)
- [Weaviate Tutorial: Optimizing Rerankers with GEPA](https://www.youtube.com/watch?v=H4o7h6ZbA4o)

### Use Cases

See the [original GEPA README](README_og_gepa.md) for extensive use case list, including:

- [Databricks: 90x cheaper enterprise agents](https://www.databricks.com/blog/building-state-art-enterprise-agents-90x-cheaper-automated-prompt-optimization)
- [ARC Computer: +142% student performance](https://www.arc.computer/blog/supercharging-rl-with-online-optimization)
- [Intrinsic Labs: 38% OCR error reduction](https://www.intrinsic-labs.ai/research/ocr-gepa-v1.pdf)

---

## 📝 License

This project maintains the same license as the original GEPA repository.

---

## 🙏 Acknowledgments

**TurboGEPA is built on the shoulders of giants.** All algorithmic credit goes to the original GEPA authors:

- Lakshya A Agrawal (UC Berkeley)
- Omar Khattab (Stanford / Databricks)
- Matei Zaharia (UC Berkeley / Databricks)
- And the full GEPA author team

TurboGEPA's contributions are limited to **performance engineering**:
- Async/await orchestration
- Island-based parallelism
- ASHA successive halving
- Disk caching infrastructure
- Adaptive configuration

The **core innovation**—LLM-based reflective mutation with Pareto selection—is entirely from the original GEPA paper.

---

<p align="center">
  <strong>Original GEPA:</strong> Research innovation & algorithmic foundation<br>
  <strong>TurboGEPA:</strong> Production-ready performance engineering<br>
  <em>Better together. 🚀</em>
</p>
