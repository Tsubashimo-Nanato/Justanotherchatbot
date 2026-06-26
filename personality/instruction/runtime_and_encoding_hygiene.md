# Runtime And Encoding Hygiene

Use this before a persona/distillation agent reloads the chatbot or edits files
that contain non-ASCII text.

## Service Ownership

The debug API, QQ loop, local model server, and remote tunnel are separate
process boundaries. Do not start a second FastAPI/debug process just because the
first one did not reload immediately.

Before a full agent restart:

1. Identify the current FastAPI process from the active instance lease or the
   listener on port `8765`.
2. Stop the current FastAPI process tree.
3. Wait until port `8765` is no longer listening.
4. Start the replacement FastAPI process.
5. Verify the new process owns the active instance lease.
6. Re-arm QQ and restart the loop only if the task requires live chat.

Do not stop the llama server on `18080` or the remote debug tunnel on `18765`
unless the task explicitly requires a full-service restart. Persona-only reloads
should usually leave model and tunnel processes alone.

## Reboot Failure Pattern

If `/api/agent/reboot` schedules a restart but the new process fails to bind
`8765`, the usual cause is that the old FastAPI process still owns the port.
Fix the lifecycle boundary instead of repeatedly launching more processes.

Correct behavior:

- stop current owner first;
- call the shared runtime process helper;
- wait for port release;
- abort the replacement start if the port is still occupied;
- log the owning process id.

When finding agent server processes, match both:

- executable path: Python or Pythonw;
- command line: `local_qq_agent.server.app:create_app`.

Do not match by command line alone. A PowerShell restart helper may contain the
uvicorn startup text in its own command line, and killing that helper interrupts
the restart before the old service is stopped.

## Encoding Checks

Persona files are UTF-8. Windows console output can still display Chinese or
Japanese text as mojibake. This is a display problem unless the source storage is
also corrupted.

Before repairing text:

1. Read the file with explicit UTF-8.
2. If the source is SQLite, read it through Python or a UTF-8-aware DB browser.
3. Compare with backups, clean run logs, or screenshots only when needed.
4. If storage is clean, do not edit the text.
5. If storage is corrupt and no known-good source exists, discard that sample
   instead of reconstructing it from guesses.

## Safe PowerShell Habits

- Prefer explicit `-Encoding UTF8` for file reads.
- Do not judge correctness from a garbled terminal render alone.
- Avoid embedding Windows paths with backslashes inside Python triple-quoted
  strings; escapes such as `\r` can turn into real control characters.
- Prefer absolute literal paths passed through a variable when generating
  PowerShell scripts from Python.

## Persona Reload Verification

After changing active profile documents or memory files:

- call the persona reload or agent reboot path;
- check persona document count, digest, or loaded timestamp;
- confirm the debug status is from the current active instance;
- confirm QQ loop state separately, because persona reload and QQ loop start are
  different operations.
