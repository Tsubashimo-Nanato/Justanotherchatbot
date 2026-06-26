# Manual Persona And Memory Edits

Use this when a human or another agent needs to adjust a persona by hand.

## Edit The Right Layer

There are three different kinds of edits:

1. Persona behavior:
   - voice, style, boundaries, interaction preferences;
   - edit active profile files under `personality/<persona>/profile/`.
2. Long-term memory:
   - stable facts that the character should remember, such as food allergies;
   - store in the memory system or the persona memory files, not in style
     anchors unless the fact changes speaking style.
3. Runtime/social state:
   - affinity, mood, temporary context, recent feedback;
   - update through the debug UI or runtime memory, not by rewriting persona
     anchors.

## Active Profile Files

Each persona should define active profile documents through config, not by
leaving many competing markdown files in its `profile/` folder.

For the current Nanato persona, active files are listed in `config/persona.yaml`.

Do not edit inactive profile files unless they are first added to the active
persona config.

For the current Nanato layout, the active profile layer is intentionally small:

- `distilled_anchor.md`: compact identity and relationship posture;
- `generated_style_anchor.md`: generated style pressure from clean logs;
- `style_learning_objective.md`: runtime learning and fitting goal;
- `runtime_boundaries.md`: safety, OOC, and operational boundaries.

If a new persona needs more files, add them deliberately to that persona's
config and document why they are active.

## Adding Long-Term Memory

Examples:

- food allergy;
- persistent preference;
- stable relationship note;
- hard boundary the bot must remember.

Add these as memory, not as style:

```text
kind: fact
scope: user
subject: <exact user display name>
summary: allergic to peanuts
source: manual_profile_edit
```

If using markdown memory files, keep one bullet per fact. Do not write a story.

## Backups

Before editing an active profile file:

1. Copy the file to a timestamped backup outside the active `profile/` load set.
2. Make the smallest edit that changes behavior.
3. Run a persona reload or service reboot if the file is already cached.

Do not leave multiple competing profile files in the active folder unless the
persona config explicitly loads them.

After editing active profile or memory documents, reload the persona before
testing. A running service may cache persona anchors until reboot/rebuild. Check
the debug persona digest or loaded timestamp instead of assuming a file save is
already live.

Service reload should use the project runtime boundary. Do not start another
FastAPI process while an old one still owns port `8765`; the reboot path must
stop the current process, wait for the port to release, and only then start the
replacement.

## What Not To Do

- Do not add raw chat logs to persona files.
- Do not add one-off events to style anchors.
- Do not put provider/API/debug implementation details in persona files.
- Do not solve a style problem by adding fixed reply templates.
- Do not enlarge the profile just because more material exists.
- Do not rewrite clean UTF-8 persona text because a Windows console displayed it
  as mojibake. Verify stored bytes/text first.
