# Token Budget And Compression Rules

Persona text is paid every time it is sent to a model unless it hits provider
cache. Small, stable, high-signal files are better than large lore dumps.

## Budget Targets

- Base anchor: under 400-700 words.
- Generated style anchor: under 1500-2500 words.
- Runtime boundaries: under 400-800 words.
- Style objective: under 300-600 words.

If a file grows past its target, compress it before adding new material.

## Compression Rules

Keep a statement only if it changes generation behavior.

Prefer:

```text
Avoid one-word dead ends after direct high-affinity messages; add one small context hook.
```

Over:

```text
On 2026-06-20 the user said the bot should not answer only "嗯?" after being called.
This happened after a shift-related conversation and shows that the bot should be more responsive.
```

The second version is useful as log evidence, not persona text.

## Delete Or Merge

Delete:

- duplicate rules;
- rules that only repeat safety boundaries already in runtime boundaries;
- examples that do not show a reusable pattern;
- old worldbuilding and decorative lore that does not affect chat behavior;
- raw quotes that are too long.

Merge:

- similar punctuation observations;
- similar "don't sound like AI" rules;
- repeated low-score reasons;
- multiple examples of the same reply failure.

## Stable Prefix

The most stable persona material should change rarely. Frequent edits reduce
prompt-cache usefulness and make behavior harder to diagnose.

Put fast-changing material in:

- runtime memory;
- clean run logs;
- behavior feedback;
- generated style anchor, after manual review.

Put slow-changing material in:

- distilled base anchor;
- runtime boundaries.

Keep volatile user facts out of stable persona files. A statement like "P001
went to a doctor today" belongs in short-term or dated memory with TTL, not in
the persona prefix. A repeated speaking habit like "drops punctuation and uses
compressed technical fragments" belongs in the style anchor.

## Final Review Checklist

Before saving a persona file:

- Can one shorter sentence replace two bullets?
- Is this a style rule, not a memory fact?
- Is the target user named exactly?
- Does the file duplicate another active file?
- Would removing this line change a reply?
- Is the rule general enough to apply next week?
- Did I verify that any apparent mojibake is stored corruption, not only
  terminal display corruption?
- Will this change preserve a stable cacheable prefix, or should it be runtime
  memory/style feedback instead?
