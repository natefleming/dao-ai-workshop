# L200 Debrief

> Reflection · L200 Building Real Agents

You've finished L200. Take a few minutes to consolidate.

## Reflect

- **Which pattern will you reach for first in your own work?** Most students gravitate to memory (Lab 7) and multi-agent (Lab 9) -- both unlock real production scenarios. Vector search (Lab 6) is the one most people underestimate; reranking is what takes RAG from demo-quality to production-quality.
- **Which guardrail philosophy fits your domain?** L200 framed guardrails for **accuracy** (don't fabricate SLAs in support). For consumer-facing agents, you'd swap the rubric for **tone** (be warm, never push products you don't have). The mechanism is identical -- a judge LLM evaluating against a registry-managed prompt.
- **Where do you still feel shaky?** Common spots: the difference between checkpointer and store in Lab 7 (short-term vs cross-session), and how `is_deterministic: true` interacts with agentic handoffs in Lab 9. Re-read the lecture if needed.

## Common gotchas you might have hit

| Gotcha | Symptom | Fix |
|---|---|---|
| Vector index missing (Lab 6) | `IndexNotFoundError` on first query | Index provisioning takes 5-10 min. The notebook waits, but if you skipped the provisioning cell, retry. |
| Genie / external API rate-limited (Lab 5) | 429 errors | The public APIs have generous free tiers but they're not infinite. Wait or reduce iteration count. |
| Memory not recalled across threads (Lab 7) | "I don't remember" in step 3 even with Lakebase | Long-term memory only fires if `extraction.background_extraction: false` AND the extraction model has time to run. Watch the trace. |
| Guardrail loops (Lab 8) | The agent retries 3 times then gives up | The judge rubric was too strict. Loosen the rubric or lower `num_retries`. |
| Supervisor routing chooses the wrong specialist (Lab 9) | tier-2 question goes to tier-1 | The `handoff_prompt:` strings need to be specific. Use concrete examples. |

## What's next: L300

L200 covered the production patterns one at a time. [**L300 Advanced**](../L300-advanced/) adds two more, each as its own focused lab:

- **Lab 11 -- Instructed Retrieval**: filter-aware retrieval with query decomposition + cross-encoder rerank + LLM-based instruction rerank.
- **Lab 12 -- Genie Context-Aware Caching**: L1 LRU exact-match cache + L2 similarity cache over a Genie tool.

(Chat-history summarization, the fourth advanced pattern, is already covered in Lab 7 alongside Lakebase memory.)

[**On to L300 → Advanced**](../L300-advanced/)
