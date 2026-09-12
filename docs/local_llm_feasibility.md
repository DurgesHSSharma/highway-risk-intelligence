# Local LLM Feasibility Assessment (Phase 1)

This is a feasibility assessment only. **No LLM runtime or model was installed
or downloaded in Phase 1** — that is Phase 2+ scope. This document exists so
the Phase 2 RAG/synthesis design starts from measured hardware facts, not
assumptions.

## Measured hardware (this machine, 2026-09-12)

Captured via [`scripts/hardware_check.py`](../scripts/hardware_check.py)
(psutil) and Windows CIM (`Win32_Processor` / `Win32_VideoController`):

| Component | Measured value |
|---|---|
| CPU | Intel Core i7-12700H — 14 physical cores / 20 logical threads, 2.3 GHz base |
| RAM | 15.69 GB total. **Only 1.42 GB was free at check time** — this machine is often running under memory pressure from other apps |
| GPU (dedicated) | NVIDIA GeForce RTX 3050 Ti Laptop GPU — 4 GB VRAM |
| GPU (integrated) | Intel Iris Xe Graphics — shares system RAM |
| Disk free | ~50 GB free on the project drive |
| OS | Windows 11 Home |

The previous planning assumption (from Phase 0) was a more constrained
"~8GB RAM, no GPU" machine. The actual measured machine is meaningfully more
capable — 16GB RAM class with a 4GB-VRAM CUDA-capable GPU — which changes what
is realistically usable for Phase 2+.

## What "free/local" LLM options exist

All zero-cost per [[project-working-rules]] — no paid API, no card-on-file
tier. The only genuinely free, local, actively-maintained runtime for GGUF
quantized models on Windows is **[Ollama](https://ollama.com)** (MIT-licensed,
runs as a local service, no account/billing required, has an NVIDIA CUDA
backend). This assessment is scoped to Ollama since it is the most
low-friction free option for this hardware; llama.cpp directly is the
underlying engine Ollama already wraps.

## Feasibility by model size (general known GGUF/Q4 sizing, not benchmarked here)

These VRAM/RAM figures are widely published approximate requirements for
4-bit quantized ("Q4") GGUF models — they are **not** measurements taken on
this machine, since no model was run in Phase 1. They should be verified with
a real timed run before being cited as fact in any later phase.

| Model class | Approx. Q4 size | Fits in 4GB VRAM (full GPU offload)? | Feasible on this machine? |
|---|---|---|---|
| ~2-3B (e.g. Llama 3.2 3B, Qwen2.5 3B, Gemma 2 2B) | ~1.5–2.2 GB | Yes | **Yes — best fit** |
| ~4B (e.g. Phi-3-mini 3.8B) | ~2.2 GB | Yes | **Yes** |
| ~7-8B (e.g. Llama 3.1 8B, Mistral 7B) | ~4.5–5 GB | Marginal — slightly over 4GB, partial CPU offload likely | **Workable but slower**, not fully GPU-resident |
| ~13B+ | ~7.5 GB+ | No | Loadable via system RAM (16GB total) but CPU-bound and slow — **not practical for interactive use** given only ~1.4GB RAM was free at measurement time |

## Recommendation for Phase 2+

Use a **3–4B class instruction-tuned model via Ollama** (e.g. Llama 3.2 3B or
Phi-3-mini) as the default for RAG answer synthesis and contradiction
summarization:

- Fully fits the 4GB RTX 3050 Ti VRAM, so inference stays GPU-accelerated.
- Leaves system RAM free for the FastAPI backend, embeddings, and vector
  index — important given this machine measured well under 2GB free RAM at
  times.
- Zero cost, no account, no network dependency once the model is pulled.

An 8B model is a plausible fallback for higher-quality synthesis if actual
timed benchmarks in Phase 2 show acceptable latency, but should not be the
default given the observed memory pressure on this machine.

**Before Phase 2 relies on any of this**, it must install Ollama, pull the
candidate model, and record real measured latency/RAM/VRAM usage — replacing
the "general known" figures in the table above with this machine's actual
numbers, per the project's no-fabrication rule.
