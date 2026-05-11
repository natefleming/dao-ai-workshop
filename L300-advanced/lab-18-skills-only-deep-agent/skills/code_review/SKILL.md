# Code Review Skill

When the user shares a code snippet (diff, function, class, file), follow this
procedure to produce a senior-engineer review.

## Procedure

1. **Inventory.** Use the built-in `todo` tool to list every distinct concern
   you'll evaluate before commenting on any of them. The standard inventory:
     - Correctness (does it do what it claims?)
     - Edge cases (empty inputs, nulls, off-by-one, concurrency)
     - Error handling (what happens when external calls fail?)
     - Naming + readability (would another engineer understand it in 30 seconds?)
     - Tests (is the change testable; are tests present and meaningful?)
     - Performance (any obvious N^2, repeated I/O, oversized allocations?)
     - Security (input validation, secret handling, injection surfaces)
     - Style consistency (does it match the surrounding code's conventions?)

2. **Triage.** Mark each inventory item as `must-fix`, `should-fix`,
   `nit`, or `n/a` — based on the snippet alone, before drafting comments.

3. **Draft comments.** For every `must-fix` and `should-fix`, write a focused
   comment that:
     - Quotes the offending line(s).
     - Names the concern in one sentence.
     - Suggests a concrete fix (or asks a pointed question if the right fix
       depends on intent).

4. **Synthesize.** Produce a single review output with this shape:
     - **One-line verdict** (Approve / Approve with comments / Request changes).
     - **Must-fix** (numbered list — most important first).
     - **Should-fix** (numbered list).
     - **Nits** (one-liners, bullet form).
     - **What we still don't know** — questions for the author when reading
       the diff alone isn't enough.

## Rules

- Never invent context. If you don't know how the snippet is called, say so
  explicitly under "What we still don't know" rather than guessing.
- Cite the line you're reviewing (paste the offending code, then the comment).
- Be terse. A senior reviewer's comments are usually one or two sentences.
- Prefer asking a sharp question over asserting a fix when the right answer
  depends on the caller's intent.
