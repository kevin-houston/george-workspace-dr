## R28 EarningsQualityAgent Amendment: Eva-4B Evasion Classifier

### Model
- HuggingFace: `FutureMa/Eva-4B-V2`  (Apache 2.0)
- GitHub: https://github.com/IIIIQIIII/EvasionBench  (inference scripts in /scripts)
- Size: 4B params (Qwen3-4B-Instruct-2507 base)
- Performance: 84.9% Macro-F1, 81.3% accuracy (vs 56.2% baseline LLM)
- Per-class F1: Direct=0.851, Intermediate=0.698, Fully_Evasive=0.873

### Integration Plan
```python
# Option A: local inference (needs ~8GB VRAM)
from transformers import pipeline
eva4b = pipeline('text-generation', model='FutureMa/Eva-4B-V2', device_map='auto')

def classify_qa_pair(question: str, answer: str) -> str:
    prompt = f'Question: {question}\nAnswer: {answer}\nClassify as direct/intermediate/fully_evasive:'
    return eva4b(prompt, max_new_tokens=10)[0]['generated_text'].strip()

def compute_noration_rate(qa_pairs: list[tuple]) -> float:
    labels = [classify_qa_pair(q, a) for q, a in qa_pairs]
    evasive_count = sum(1 for l in labels if l in ('intermediate', 'fully_evasive'))
    return evasive_count / len(labels) if labels else 0.0
```

### Position Sizing Rule (unchanged from prior heuristic)
- NOR_rate > 0.25 AND institutional_ownership_pct > 50%: upsize PEAD position by 1.5x
- NOR_rate > 0.40: upsize by 1.75x (management hiding more = longer drift)
- NOR_rate < 0.10: baseline size (management fully responsive = faster price discovery)

### If Local Inference Not Available (fallback)
Use EvasionBench dataset labels for historical backtesting (16,726 Q&A pairs):
  from datasets import load_dataset
  ds = load_dataset('FutureMa/EvasionBench')
  # Filter for tickers in our PEAD universe, merge on earnings date

### Key Citation Evidence
- '40pp rise in response incoherence -> 0.74% drop in 1-day returns' (EvasionBench paper)
- '63% likelihood of underperformance within 180 days' for high-evasion companies
- This CONFIRMS our NOR heuristic direction (evasion = slower price discovery = longer drift window)
