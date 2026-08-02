---
title: AirLLM — Layer-wise Streaming Inference for Huge Models on Small GPUs
added: 2026-08-02
category: tools
url: https://github.com/lyogavin/airllm
---

# AirLLM

Open-source library enabling inference of very large LLMs on small consumer
GPUs via "layer-wise inference" — layers (or, for MoE models, individual
experts) are decomposed to disk and streamed onto the GPU one at a time, so
VRAM requirement scales with the *largest single layer/expert*, not total
parameter count. No quantization/distillation/pruning required for the base
technique (optional 4/8-bit block compression offered separately for ~3x
speedup). Surfaced via a viral tweet (@thesupermanmx, 2026-08-01) claiming
Kimi K3 (2.8T params) running under 4GB VRAM.

**Stars:** 25,106 | **Forks:** 2,832 | **License:** Apache 2.0 | **Language:**
Python (Jupyter-notebook-heavy examples) | **Created:** June 2023 | **Last
push:** 2026-07-29 — actively maintained (Kimi K3 support added July 2026,
FP8 support v3.0 June 2026)

## What it does

- **Layer-wise streaming**: dense models stream one layer at a time;
  MoE models (Qwen3-235B, DeepSeek-V3, Kimi K3) stream per-*expert*, which is
  why MoE models fit in even less VRAM relative to their size.
- Verified against README, tweet's claims are accurate, not exaggerated:
  Llama 3.1 405B on ~8GB, DeepSeek-V3 671B on ~12GB, Qwen3-235B MoE on ~3GB,
  Kimi K3 2.8T on 3.72GB (measured on one RTX 6000 Ada).
- Near drop-in HuggingFace Transformers replacement:
  ```python
  from airllm import AutoModel
  model = AutoModel.from_pretrained("Qwen/Qwen3-32B")
  out = model.generate(input_ids.cuda(), max_new_tokens=20)
  ```
  `pip install airllm` (PyPI, v3.1.0). Supports Llama 2/3/3.1/3.3/4, Qwen 1-3,
  DeepSeek V2/V3/R1, Mistral/Mixtral, Phi, Gemma, ChatGLM, Baichuan, InternLM.

## Caveats

- **Not documented in the README but inherent to the approach**: repeated
  disk/CPU→GPU transfer per layer per forward pass is a real latency tax —
  optimized for feasibility (running a model at all), not throughput. No
  tokens/sec benchmarks published.
- First load re-splits the model into layer shards on disk — needs roughly
  the model's full size in free disk space (more if keeping the original
  copy; use `delete_original=True` to avoid duplication).
- Best suited for occasional/experimental huge-model inference or batch/
  offline single-prompt jobs on consumer hardware — not low-latency or
  high-throughput production serving.
- Kimi K3 support has extra dependencies (`compressed-tensors`, `flash-attn`,
  CUDA 12 — no CUDA 13 flash-attn wheel yet, `transformers` 4.56.x pinned).

## Assessment

Not a fundamentally novel technique — same family as DeepSpeed ZeRO-Infer/
ZeRO-Offload and llama.cpp's mmap/disk offloading (stream weights instead of
holding them all in VRAM). AirLLM's value-add is packaging: a single
`pip install` + HF-compatible `AutoModel` API with near-zero config, vs.
DeepSpeed's heavier setup surface. A convenience/accessibility layer over an
established technique, not a new inference algorithm.

## Relevance to George's Stack

Low/speculative. Not trading-specific. Could matter if Kevin ever wants to
self-host a large open-weight model (e.g. for FinBERT-adjacent NLP work, or
cost-avoidance vs. OpenAI API calls) on modest hardware — but the latency
tradeoff makes it unsuitable for anything latency-sensitive like the PEAD
intraday scanner. Logged for reference, no action recommended now.

# Citations

- Tweet: https://x.com/thesupermanmx/status/2083492978891661658
- Repo: https://github.com/lyogavin/airllm
