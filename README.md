# Local QQ Agent Demo

This repository is a first-pass local agent architecture for a configurable persona chatbot that can run against a local open model, keep SQLite-backed memory, inspect a manually opened QQNT group window, and expose a small FastAPI debug UI.

The first implementation favors clear boundaries over a large framework:

- model calls use an OpenAI-compatible HTTP endpoint;
- SQLite is the durable memory source;
- QQ sending is disabled until explicitly armed;
- web search goes through SearXNG, with browser reading kept read-only and allowlisted;
- `workspace/` holds only project handoff markdown files.
- Runtime artifacts, scripts, tests, and model downloads live outside `workspace/`.

## Quick Start

```powershell
py -V:Astral/CPython3.12.10 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,browser]"
.\.venv\Scripts\python -m pip install "llama-cpp-python[server]==0.3.30" --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
.\.venv\Scripts\python -m pip install "nvidia-cuda-runtime-cu12==12.4.127" "nvidia-cublas-cu12==12.4.5.8" "nvidia-cuda-nvrtc-cu12==12.4.127"
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m uvicorn local_qq_agent.server.app:create_app --factory --host 0.0.0.0 --port 8765
```

Then open `http://127.0.0.1:8765/debug` on this machine, or `http://<this-machine-LAN-IP>:8765/debug` from another device on the same LAN.

For normal local use, double-click:

```text
deploy.bat
```

It starts the active hybrid llama server, the FastAPI debug server, prints the local and LAN debug URLs, and writes runtime logs under `artifacts/runtime/`. It does not open a new browser tab. SearXNG is optional and starts only when `LOCAL_QQ_AGENT_START_SEARXNG=1`.

By default `deploy.bat` binds the debug server to `0.0.0.0:8765` so same-LAN devices can use the debug UI. The model server remains bound to `127.0.0.1:18080`; do not expose the model API unless you add a separate access-control layer. To force the debug UI back to localhost-only, set `$env:LOCAL_QQ_AGENT_HOST = "127.0.0.1"` before running `deploy.bat`.

To stop the demo services, double-click:

```text
stop.bat
```

## Model

The model config supports named profiles in `config/model.yaml`. The active profile is served through the OpenAI-compatible endpoint at `http://127.0.0.1:18080/v1`.

Current configured profiles:

- `qwen3-14b-q4`: older latency-focused baseline.
- `qwen3-30b-a3b-instruct-2507-q4`: higher-quality 30B-A3B profile, but too large for stable low-latency 12GB VRAM use on the current machine.
- `qwen3-30b-iq2m-hybrid-high`: active hybrid RAM/VRAM 30B-A3B IQ2_M profile for local gate and utility calls.
- `qwen3-30b-a3b-instruct-2507-iq2m`: lower-quantization 30B-A3B profile kept as a compatibility alias.

Download the GGUF:

```powershell
.\.venv\Scripts\python scripts\download_model.py
.\.venv\Scripts\python scripts\download_model.py --profile qwen3-30b-a3b-instruct-2507-iq2m
```

Start a local server with llama-cpp-python after the model is present:

```powershell
$env:PATH = "$PWD\.venv\Lib\site-packages\nvidia\cuda_runtime\bin;$PWD\.venv\Lib\site-packages\nvidia\cublas\bin;$PWD\.venv\Lib\site-packages\nvidia\cuda_nvrtc\bin;$env:PATH"
.\.venv\Scripts\python -c "from local_qq_agent.config import ModelConfig; from local_qq_agent.model.manager import restart_llama_server; import json; print(json.dumps(restart_llama_server(ModelConfig.load()), ensure_ascii=False, indent=2))"
```

The default demo path now uses a hybrid provider: local llama.cpp handles low-latency gate, placeholder, and feedback classification calls; Grok is reserved for final replies when `XAI_API_KEY` is configured. The local model profile uses 8k context and partial GPU layer offload to avoid filling 12GB VRAM.

The current verified local path uses the `cu124` llama-cpp-python wheel plus the CUDA runtime DLL packages listed above. On the RTX 4070 Ti test machine, a short `/api/chat/simulate` call dropped from the old CPU path to about 1.2 seconds wall time, with full model offload reported by the llama server logs.

The debug UI has `Provider` and `Model` panels. Provider `hybrid` means local gate/utility plus Grok final replies. `Load profiles` shows installed profiles and `Switch model` downloads the selected GGUF if needed, restarts the local llama server, rebuilds the agent, reloads the current persona, and keeps the active personality SQLite memory/context database. The `.status` command also reports the current active model/profile.

## SearXNG

```powershell
docker compose -f docker-compose.searxng.yml up -d
```

The agent expects SearXNG at `http://127.0.0.1:8888`.

## Verification Commands

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\hardware_diagnostics.py
.\.venv\Scripts\python scripts\model_smoke.py
.\.venv\Scripts\python scripts\qq_probe.py
```

QQ sending is blocked unless both conditions are true:

- `config/qq.yaml` has `dry_run: false`;
- `/api/qq/arm` has been called in the current server process.
- the active QQ group name exactly matches `config/qq.yaml expected_group_name`.

## QQ Window Use

1. Open the intended QQ group window manually and leave it visible.
2. Run `deploy.bat`.
3. Open `http://127.0.0.1:8765/debug` locally, or use the LAN URL printed by `deploy.bat` from another device.
4. Click `Probe window`; this only reads the current QQ window structure.
5. Click `Arm`.
6. For manual send testing, type text in `QQ text` and click `Send through QQ adapter`.
7. For automatic reply testing, click `Start loop`. The loop reads the visible QQ message list and only reacts to `target_sender_name` in `config/qq.yaml`.

The checked-in demo config uses safe placeholders and `dry_run: true`. Set `expected_group_name`, `target_sender_name`, `bot_sender_name`, and any `bot_sender_aliases` for your own QQ test group before real sends. `bot_sender_name` and aliases are used to exclude the agent's own QQ messages from the polling loop. If either the group name or armed state is wrong, the send is refused and the debug page shows the refusal in the Result panel and Output JSON.

The adapter prefers a QQ popout conversation window whose title matches `expected_group_name`. If that popout exists, it is used instead of the main QQ window. When the popout is minimized, read/send operations restore it, focus it, scroll to the latest visible messages, then minimize it again after the operation.

When the loop starts, it marks currently visible target-user messages as history and does not reply to them. During polling it records visible chat as context, queues unseen target-user messages, and processes queued messages one by one. Queue state and decisions are written to the debug event log.

The QQ loop is careful by default. A message from `target_sender_name` is not enough by itself; the attention gate decides whether the character would naturally answer under the current context, short-term memory, durable memory, activity setting, and interruption risk. Status descriptions or casual fragments are not automatically refused, but messages clearly aimed at someone else or likely to cut into another conversation should become `no_reply` and send nothing.

## QQ Loop Commands

Commands are dot suffixes appended to the end of an incoming QQ message. They are stripped before the text is sent to the model. Old `#e`, `#d`, and `#i` suffixes are deprecated and are now treated as normal text.

- `.enforce`: forced reply. The agent must call the language model and reply even if the message would normally be skipped.
- `.detail`: debug reply. The QQ reply includes elapsed time, model latency, completion token/sec, prompt tokens, completion tokens, total tokens, thinking level, and web usage.
- `.debug`: diagnostic reply. The QQ reply includes a compact diagnostic summary with event id, clean-turn reason, removed-line count, requested/effective thinking, web query, and source count. Full raw metadata stays in the debug UI/event log.
- `.ignore`: ignore completely. The agent skips memory write, model inference, and QQ send.
- `.think`: current message uses thinking level `1`, the lowest explicit thinking budget.
- `.think 0|1|2|3`: current message thinking level. `0` means automatic selection from message complexity; `1`, `2`, and `3` force that level for the current message.
- `.help`: standalone help command. It does not call the model and must be the whole message.
- `.status`: standalone status command. It does not call the model and reports runtime settings, social state, and persona reload policy.
- `.reboot`: standalone agent-only reboot command. It restarts the FastAPI agent service so changed personality files are loaded, while keeping the local model server running.
- `.score 0..1 [reason]`: standalone feedback command for the previous reply. It records behavior feedback in memory without changing personality files and sends no QQ reply. Compact form such as `.score0.3 打断` is also accepted.

Runtime setting commands are standalone messages:

- `.set .think 0|1|2|3`: change the default thinking level for future messages. `0` means automatic; `1`, `2`, and `3` force that default level.
- `.set .activity 0..1`: change reply willingness. `0` silences non-enforced messages; higher values allow the attention gate to reply more readily.

Settings can be combined:

```text
.set .think 0 .activity 0.25
```

Suffix commands can be combined in any order, for example:

```text
hello .detail .debug .think 2 .enforce
```

Commands in the middle of a sentence are plain text. Without `.detail` or `.debug`, the QQ reply only contains the model reply text. Full metadata is still stored in the debug UI and event log.

`.score` is for behavior correction, not personality editing. A low score with a reason such as `打断` tells the agent that the previous reply was poorly timed or inappropriate; the feedback becomes `behavior_feedback` memory for future attention/reply decisions. Low scores below `0.35` with a reason are also appended to the active profile's `memory/behavior_feedback.jsonl` for later review by a separate personality agent. They do not rewrite personality anchors.
# Nanato Persona Runtime Learning

The current Nanato profile uses a compressed, low-weight anchor under `personality/nanato/profile/`. A backup of the previous profile directory is kept under `personality/nanato/profile_backup_*`.

Runtime style learning is configured in `config/persona.yaml`:

- `style_learning.target_user: Tsubashimo Nanato`
- `base_anchor_weight: low`
- `proactive_topic_bias: 0.68`

Recent messages from the target user are projected as compact style samples. The agent learns timing, wording, language mix, and feedback pressure at runtime, but it does not rewrite persona anchor files. When the QQ loop stops, a cleaned iteration log is written to `personality/nanato/memory/runtime/run_logs/` for later review or persona-agent training.

## Social Profiles And Style Logs

Social profiles are created automatically from visible QQ sender names and interaction events. The debug UI Social panel lists detected users, lets you select one, and edits that user's runtime affinity/profile separately from global mood and global affinity. The target user starts at high affinity by config/runtime seeding; other discovered users start neutral unless memory already says otherwise.

Run-stop logs are `RunSessionLog` artifacts, not raw database dumps. They keep only training-useful events such as clean user messages, bot replies, no-reply decisions, placeholders, behavior feedback, and compact web/tool summaries. They deliberately exclude prompts, API keys, raw provider traces, SQLite dumps, model files, and private reference material.

The current style-learning path is an iteration harness:

1. Run the QQ loop and collect clean interaction events.
2. Stop the loop to export `personality/nanato/memory/runtime/run_logs/run_log_*.json`.
3. Review `.score` feedback and the log's `style_learning` summary.
4. A later personality/style agent may produce a style-memory or persona proposal.

This project does not train or fine-tune a model in v0.01, and runtime feedback does not rewrite persona anchor files automatically.

## Public 0.01 Boundary

The public repository is sanitized source only. `.gitignore` excludes `.env`, model downloads, artifacts, runtime SQLite databases, exported run logs, root `workspace/` handoff files, personality references, profile backups, and personality runtime temp files.

Release `0.01` is the first source snapshot. After it, new work should be done on feature branches such as `feature/social-users`, `feature/style-learning-loop`, or `feature/qq-ingestion-cleanup`.
