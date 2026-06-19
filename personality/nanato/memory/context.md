# Context Assembly

Context is assembled from the current visible QQ message, recent short-term
conversation, durable SQLite memories, optional tool results, and web evidence.

Order of precedence:

1. Persona/OOC boundary rules.
2. Current user message and current QQ group target.
3. Recent conversation that the agent actually participated in.
4. Relevant long-term SQLite memories.
5. Ephemeral tool/web context for the current turn.
6. Behavior feedback that affects timing, relevance, and tone.

Messages that the agent chose not to answer should not become conversational
context unless they are later promoted into memory for a clear reason.
