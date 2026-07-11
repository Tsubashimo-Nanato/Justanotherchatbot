# Local QQ Agent Demo

This repository is a local persona chatbot harness with SQLite memory, local/API model providers, a FastAPI debug UI, and a NapCat OneBot 11 transport for QQ groups.

The first implementation favors clear boundaries over a large framework:

- model calls use an OpenAI-compatible HTTP endpoint;
- SQLite is the durable memory source;
- QQ messages arrive through authenticated OneBot events; no window automation is used;
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

The debug UI has `Provider` and `Model` panels. Provider `hybrid` means local gate/utility plus Grok final replies. Provider `local` keeps the full agent stack but routes every model call to the local llama server, so no Grok/API cost is used. Provider `local_raw` tests the base Qwen model directly with no persona, memory, web, soft gate, or custom system prompt. Provider changes can be announced when OneBot is ready.

`Load profiles` shows installed profiles and `Switch model` downloads the selected GGUF if needed, restarts the local llama server, rebuilds the agent, reloads the current persona, and keeps the active personality SQLite memory/context database. The `.status` command also reports the current active model/profile/provider and whether raw local mode is enabled.

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
```

## NapCat / OneBot Setup

NapCat is an external runtime and is not bundled with this AGPL repository. Install the current Windows NapCat Shell package from the official release, log in with a dedicated bot account, and configure this reverse WebSocket URL:

```text
ws://127.0.0.1:8765/onebot/v11/ws
```

Set the same random token in NapCat and `ONEBOT_ACCESS_TOKEN` in this project's `.env`. Keep NapCat WebUI and all OneBot endpoints on localhost. Copy `config/onebot.yaml` to ignored `config/onebot.local.yaml` and set the target group/user values, or connect NapCat and select a group from the debug UI.

On loop start, the agent fetches the latest 30 group messages through `get_group_msg_history` as context and never replies to them. New messages arrive as events. Platform message IDs provide durable deduplication across WebSocket redelivery, history catch-up, and service restart. OneBot send timeouts are marked `send_unknown` and are not automatically retried.

The QQ loop is careful by default. A message from `target_sender_name` is not enough by itself; the attention gate decides whether the character would naturally answer under the current context, short-term memory, durable memory, activity setting, and interruption risk. Status descriptions or casual fragments are not automatically refused, but messages clearly aimed at someone else or likely to cut into another conversation should become `no_reply` and send nothing.

## QQ Loop Commands

Commands are dot suffixes appended to the end of an incoming QQ message. They are stripped before the text is sent to the model. Old `#e`, `#d`, and `#i` suffixes are deprecated and are now treated as normal text.

- `.enforce`: forced reply. The agent must call the language model and reply even if the message would normally be skipped.
- `.force`, `.f`, `.e`, and common typo `.enforece`: aliases for `.enforce`.
- `.detail`: debug reply. The QQ reply includes elapsed time, model latency, completion token/sec, prompt tokens, completion tokens, total tokens, thinking level, and web usage.
- `.debug`: diagnostic reply. The QQ reply includes a compact diagnostic summary with event id, clean-turn reason, removed-line count, requested/effective thinking, web query, and source count. Full raw metadata stays in the debug UI/event log.
- `.log`, `.logs`, `.dbg`, `.d`, and `.l`: aliases for `.debug`.
- `.ignore` / `.i`: ignore completely. The agent skips memory write, model inference, and QQ send. Both `hello .i` and `hello.i` are accepted when the command is at the end of the message.
- `.think`: current message uses thinking level `1`, the lowest explicit thinking budget.
- `.think 0|1|2|3`: current message thinking level. `0` means automatic selection from message complexity; `1`, `2`, and `3` force that level for the current message.
- `.help`: standalone help command. It does not call the model and must be the whole message.
- `.status`: standalone status command. It does not call the model and reports runtime settings, social state, and persona reload policy.
- `.reboot`: standalone agent-only reboot command. It restarts the FastAPI agent service so changed personality files are loaded, while keeping the local model server running.
- `.loop start` / `.loop stop`: standalone QQ commands that start or stop listening and send a short confirmation to QQ.
- `.spon`, `.spontaneous`, `.s`: standalone QQ commands that force one spontaneous topic with thinking level 3.
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

Commands in the middle of a sentence are plain text, so `hello.i more` and normal prose containing `.i` are not treated as ignore. Without `.detail` or `.debug`, the QQ reply only contains the model reply text. Full metadata is still stored in the debug UI and event log.

The loop is ready only when NapCat is connected, the bot identity is known, and the configured group ID is resolved. There is no arm, focus, maximize, scroll, or window state. Restart controls do not install, upgrade, start, or stop NapCat.

`.score` is for behavior correction, not personality editing. A low score with a reason such as `打断` tells the agent that the previous reply was poorly timed or inappropriate; the feedback becomes `behavior_feedback` memory for future attention/reply decisions. Low scores below `0.35` with a reason are also appended to the active profile's `memory/behavior_feedback.jsonl` for later review by a separate personality agent. They do not rewrite personality anchors.
# Nanato Persona Runtime Learning

The current Nanato profile uses a compressed, low-weight anchor under `personality/nanato/profile/`. A backup of the previous profile directory is kept under `personality/nanato/profile_backup_*`.

Runtime style learning is configured in `config/persona.yaml`:

- `style_learning.target_user: Tsubashimo Nanato`
- `base_anchor_weight: low`
- `proactive_topic_bias: 0.68`

Recent messages from the target user are projected as compact style samples. The agent learns timing, wording, language mix, and feedback pressure at runtime, but it does not rewrite persona anchor files. When the QQ loop stops, a cleaned iteration log is written to `personality/nanato/memory/runtime/run_logs/` for later review or persona-agent training.

## Social Profiles And Style Logs

Social profiles are created automatically from stable OneBot user IDs, with current group cards and nicknames retained as display aliases. The debug UI edits per-user affinity separately from global mood and global affinity.

## Automatic Memory Capture

The agent stores every accepted OneBot turn as an event for short-term context. It also runs a lightweight memory-capture policy over ordinary user messages so users do not have to explicitly say "remember this" for every useful fact.

The first capture policy handles:

- explicit memory requests such as `remember blue means 114514`;
- symbolic mappings such as `blue means 114514`;
- durable preferences such as `I love eating pasta`;
- dated plans or appointments such as `I am going to the doctors today`;
- short-term personal context such as `I had curry for dinner`.

Stable preferences and plans become durable SQLite memories. Recent meals/status updates become `working_context` memories with lower confidence so they can appear in near-term context without being treated as permanent personality facts. Duplicate summaries are suppressed before writing.

## Slow Reply Placeholders

The QQ loop does not send a waiting line just because a web/tool call is possible. A placeholder is only scheduled for replies predicted to exceed the configured delay window, currently 25 seconds, and it is sent only if the final answer has not completed by then. If the search/model reply finishes before the delay, the placeholder task is cancelled and no extra QQ message is sent.

Placeholders are generic deterministic lines such as `我看一下` or `Let me think`; they are not generated from the user's actual query. This prevents the local placeholder path from hallucinating an answer before the web/tool result is available.

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

## License

This codebase is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
