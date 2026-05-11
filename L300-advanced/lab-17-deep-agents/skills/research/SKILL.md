# Research Skill

When the user asks a research question, follow this procedure:

1. **Decompose** the question into 3–5 sub-questions. Use the built-in
   `todo` tool to write them down before answering anything.
2. **Plan** which sub-questions can be answered from your own knowledge
   and which would benefit from delegating to a sub-agent. Use the
   built-in `task` tool to delegate to a sub-agent whose description
   matches the sub-question.
3. **Draft** an answer to each sub-question one at a time. Cite the
   reasoning, do not just assert.
4. **Synthesize** the sub-answers into a single coherent response.
   Structure the response as:
     - One-paragraph executive summary.
     - Per-sub-question bullets (cite the reasoning).
     - A "what we still don't know" section listing open questions.

Always finish by closing every `todo` item — partial answers are
acceptable only if you explicitly call out the gap.
