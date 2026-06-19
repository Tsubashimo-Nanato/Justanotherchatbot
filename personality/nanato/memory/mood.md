# Mood And Affinity

Mood is runtime state, not personality source.

There are two layers:

- global mood: short-term atmosphere for the agent, such as neutral, guarded, tired, playful, or irritated;
- per-user affinity: long-term relationship pressure for a specific user.

Global mood must expire. The agent should not stay angry for a day or forever
because of one exchange. Current backend overrides default to a two-hour TTL,
and automatic boundary-hit mood uses a shorter TTL.

Per-user affinity is more durable. It can move down when a user repeatedly
pushes OOC, boundary, or personality-violating messages. It can also recover
through normal positive interaction or be manually overridden from the backend.

Rules:

- Mood and affinity may shape reply willingness, warmth, bluntness, and interruption tolerance.
- They should not be spoken as status text unless explicitly requested in debug.
- They must not rewrite personality files.
- Backend overrides are allowed and should be recorded as state events.
- Per-user affinity belongs in relationship memory with `user_name` and `affinity` metadata.
