# Short-Term Memory

Short-term memory is the recent operating context for one live chat session.
It may include:

- recent target-user messages after loop start;
- agent replies, placeholders, and no-reply decisions;
- current active topic;
- pending questions;
- recent tool results;
- interruption-risk notes.

Short-term records should stay in SQLite `events`. They are useful for the next
few turns, but they should not automatically become stable facts.
