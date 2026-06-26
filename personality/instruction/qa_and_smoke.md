# QA And Smoke For Persona Distillation

Every style distillation update needs a small quality check. The goal is not to
prove the model is perfect; it is to catch obvious regressions before runtime.

## Required Read-Only Inspection

Before changing a style anchor, inspect:

- the active persona config;
- current generated style anchor;
- latest clean run logs;
- recent behavior feedback;
- recent bot replies that received low score;
- recent repeated bot replies;
- social/user profile for the target display name.

Do not use raw noisy logs unless no clean export exists.

Also inspect encoding before editing:

- confirm active profile files can be read as UTF-8;
- confirm target-user samples are clean in the source file or SQLite record;
- treat terminal mojibake as display failure until storage corruption is proven;
- discard unrecoverable corrupted samples instead of training the persona to
  emit mojibake.

## Smoke Samples

After generating a new anchor, test a small set of prompts without sending to
QQ. Replace the target/non-target names with the exact persona profile names.

```text
<target name> 在干嘛
我下班了
刚刚说的是哪种面
你能不能多说几个字，token那么宝贵吗
没在和你说话
查一下今天江东区会不会下雨
<non-target user>: 呜呜呜都说很有特点呜呜呜
previous bot reply: 还行…你呢？
new target message: 昨晚没睡好 好困，在去医院的路上
```

For another persona or another target user, replace samples with equivalent
recent patterns from that user's logs.

## QA Criteria

Pass:

- exact target user is named in the style anchor;
- replies preserve the user's rhythm without copying long raw messages;
- direct questions answer the concrete message first;
- follow-up questions use recent context;
- current-fact answers do not sound like pasted search results;
- no raw logs, API traces, system prompts, or debug data appear in persona text;
- generated anchor is smaller or more compressed than the source material;
- service reload plan is clear if the running agent caches persona files;
- non-target users do not receive target-user intimacy;
- a recent exact bot reply is not reused for a different turn;
- life/status turns are not answered with generic comfort unless the target
  user's style supports that in context.

Fail:

- the anchor stores personal events as style;
- the bot claims to be the target user;
- the anchor grows into a transcript dump;
- the reply style becomes generic assistant text;
- QA samples show obvious wrong-context or dead-end replies;
- mojibake appears in active persona text or style samples;
- commands/debug output are treated as personality.

## Report Format

```text
persona: <persona id>
target_user: <exact display name>
sources_checked:
  - <path or event range>
changes:
  - <style change>
excluded_memory_facts:
  - <fact or "none">
qa:
  passed: true|false
  notes: <short>
runtime:
  reload_required: true|false
  loaded_digest_or_timestamp: <value or "not checked">
```
