# Capability Layer

The agent is a chat character first, but it can use bounded local capabilities
when a reply would otherwise be wrong, stale, or needlessly weak.

Current implemented capabilities:

- web search and allowlisted browser reading for current facts;
- local math scratch work for calculation-style messages;
- QQ window read/send through the guarded adapter.

Rules:

- Capability use happens after the attention gate decides the agent should reply.
- Capability output is evidence for the final message, not the final voice.
- The final reply must be written in the character's normal conversational style.
- Tool results should be recorded as short-term events unless explicitly promoted.
- Scratch files go under `personality/nanato/workspace/temp/` and must be cleaned up.

Future capabilities can include richer symbolic math, small local Python scratch
tasks, file inspection, timers, or structured note taking. Each new capability
needs a bounded input contract and failure behavior before it is connected to QQ.
