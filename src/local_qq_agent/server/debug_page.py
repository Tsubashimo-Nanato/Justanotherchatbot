DEBUG_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local QQ Agent Debug</title>
  <style>
    :root {
      color-scheme: light;
      font-family: "Segoe UI", system-ui, sans-serif;
      line-height: 1.45;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --line: #d8dee4;
      --muted: #57606a;
      --text: #1f2328;
      --green: #1f883d;
      --red: #cf222e;
      --blue: #0969da;
      --dark: #0d1117;
      --code: #e6edf3;
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-width: 0;
      overflow-x: hidden;
      background: var(--bg);
      color: var(--text);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 20px;
      font-weight: 650;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 15px;
    }
    h3 {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    p {
      margin: 8px 0;
      color: var(--muted);
      font-size: 13px;
    }
    label {
      display: block;
      margin: 10px 0 4px;
      font-size: 13px;
      color: var(--muted);
    }
    input, textarea, select, button {
      width: 100%;
      min-width: 0;
      font: inherit;
    }
    input, textarea, select {
      border: 1px solid #d0d7de;
      border-radius: 6px;
      padding: 8px;
      background: #ffffff;
      color: var(--text);
    }
    input[type="checkbox"] {
      width: auto;
      margin-right: 6px;
    }
    textarea {
      min-height: 86px;
      resize: vertical;
    }
    button {
      border: 1px solid var(--green);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--green);
      color: white;
      cursor: pointer;
      white-space: normal;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    button.secondary {
      border-color: #8c959f;
      background: #f6f8fa;
      color: var(--text);
    }
    button.danger {
      border-color: var(--red);
      background: var(--red);
    }
    button.tab-button {
      border-color: var(--line);
      background: #f6f8fa;
      color: var(--text);
      text-align: left;
      font-size: 13px;
    }
    button.tab-button[aria-selected="true"] {
      border-color: var(--blue);
      background: #ddf4ff;
      color: #0550ae;
      font-weight: 650;
    }
    pre {
      width: 100%;
      min-height: 160px;
      max-height: 520px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 0;
      padding: 12px;
      border-radius: 6px;
      background: var(--dark);
      color: var(--code);
      font-size: 12px;
    }
    details {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f6f8fa;
      padding: 10px;
    }
    summary {
      cursor: pointer;
      font-weight: 650;
    }
    main {
      width: min(100%, 1660px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      padding: 14px;
    }
    section, .panel {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .top-status {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 8px;
    }
    .status-pill {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      background: #f6f8fa;
      font-size: 12px;
    }
    .status-pill strong {
      display: block;
      color: var(--muted);
      font-weight: 600;
    }
    .status-pill span {
      display: block;
      margin-top: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    .layout {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }
    .tabs {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 8px;
      align-self: start;
    }
    .workspace {
      min-width: 0;
      display: grid;
      gap: 14px;
    }
    .tab-panel {
      display: none;
      gap: 14px;
    }
    .tab-panel.active {
      display: grid;
    }
    .console {
      min-width: 0;
      display: grid;
      gap: 14px;
      align-self: start;
    }
    .console-card {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .console-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }
    .actions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 0 12px;
    }
    .compact-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .compact-textarea {
      min-height: 72px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #f6f8fa;
      min-height: 70px;
    }
    .metric .label {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .metric .value {
      display: block;
      margin-top: 6px;
      font-size: 16px;
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .summary-box {
      min-height: 96px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      padding: 12px;
      border: 1px solid #d0d7de;
      border-radius: 6px;
      background: #f6f8fa;
      color: var(--text);
      font-size: 14px;
    }
    .activity {
      min-height: 96px;
      margin-top: 10px;
      font-size: 13px;
    }
    .message-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .message-item {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #f6f8fa;
      color: var(--text);
      text-align: left;
      cursor: pointer;
    }
    .message-item strong {
      display: block;
      margin-bottom: 3px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .message-item span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .chat-window {
      display: grid;
      gap: 10px;
      max-height: 520px;
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef1f4;
    }
    .chat-bubble {
      width: min(82%, 680px);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #ffffff;
      color: var(--text);
      text-align: left;
      cursor: pointer;
    }
    .chat-bubble.agent {
      justify-self: end;
      background: #dff6dd;
    }
    .chat-bubble.decision {
      justify-self: center;
      width: min(92%, 760px);
      background: #f6f8fa;
      color: var(--muted);
      cursor: default;
    }
    .debug-chat-controls {
      display: grid;
      grid-template-columns: minmax(160px, 1fr) minmax(120px, 180px);
      gap: 10px;
      align-items: end;
    }
    .credential-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
    }
    .credential {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #f6f8fa;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 12px;
    }
    .chat-bubble.selected {
      outline: 2px solid var(--blue);
    }
    .chat-meta {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 11px;
    }
    .chat-text {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .chat-detail {
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .mono-small {
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 12px;
    }
    .inline-value {
      float: right;
      color: var(--text);
      font-variant-numeric: tabular-nums;
    }
    .danger-zone {
      border-color: #ffebe9;
      background: #fff8f8;
    }
    .split {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }
    @media (min-width: 760px) {
      .form-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .wide {
        grid-column: 1 / -1;
      }
    }
    @media (min-width: 1180px) {
      .layout {
        grid-template-columns: 190px minmax(0, 1fr) minmax(420px, 560px);
        align-items: start;
      }
      .tabs {
        position: sticky;
        top: 116px;
        grid-template-columns: 1fr;
      }
      .console {
        position: sticky;
        top: 116px;
        max-height: calc(100vh - 132px);
        overflow: auto;
      }
      .console-grid {
        grid-template-columns: 1fr;
      }
      .split {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>Local QQ Agent Debug</h1>
    <div id="topStatus" class="top-status">
      <div class="status-pill"><strong>Model</strong><span id="topModel">not loaded</span></div>
      <div class="status-pill"><strong>Provider</strong><span id="topProvider">unloaded</span></div>
      <div class="status-pill"><strong>API Usage</strong><span id="topApiUsage">0 / ?</span></div>
      <div class="status-pill"><strong>OneBot</strong><span id="topQQ">disconnected</span></div>
      <div class="status-pill"><strong>Loop</strong><span id="topLoop">unknown</span></div>
      <div class="status-pill"><strong>Queue</strong><span id="topQueue">unknown</span></div>
      <div class="status-pill"><strong>Active</strong><span id="topActive">none</span></div>
      <div class="status-pill"><strong>Latest</strong><span id="topLatest">none</span></div>
    </div>
  </header>

  <main>
    <div class="layout">
      <nav class="tabs" role="tablist" aria-label="Debug sections">
        <button id="tab-overview" class="tab-button" role="tab" aria-controls="panel-overview" onclick="activateTab('overview')">Overview</button>
        <button id="tab-chat" class="tab-button" role="tab" aria-controls="panel-chat" onclick="activateTab('chat')">Chat Test</button>
        <button id="tab-debug-chat" class="tab-button" role="tab" aria-controls="panel-debug-chat" onclick="activateTab('debug-chat')">Debug Chat</button>
        <button id="tab-qq" class="tab-button" role="tab" aria-controls="panel-qq" onclick="activateTab('qq')">OneBot / Loop</button>
        <button id="tab-provider" class="tab-button" role="tab" aria-controls="panel-provider" onclick="activateTab('provider')">Provider</button>
        <button id="tab-model" class="tab-button" role="tab" aria-controls="panel-model" onclick="activateTab('model')">Model</button>
        <button id="tab-settings" class="tab-button" role="tab" aria-controls="panel-settings" onclick="activateTab('settings')">Settings / Social</button>
        <button id="tab-memory" class="tab-button" role="tab" aria-controls="panel-memory" onclick="activateTab('memory')">Memory</button>
        <button id="tab-web" class="tab-button" role="tab" aria-controls="panel-web" onclick="activateTab('web')">Web</button>
        <button id="tab-logs" class="tab-button" role="tab" aria-controls="panel-logs" onclick="activateTab('logs')">Logs</button>
      </nav>

      <div class="workspace">
        <div id="panel-overview" class="tab-panel" role="tabpanel" aria-labelledby="tab-overview">
          <section>
            <h2>Overview</h2>
            <p>Refresh checks model, memory, OneBot, web and loop state. Runtime shows process, GPU and latest token metrics.</p>
            <div class="actions">
              <button id="refreshButton" onclick="loadStatus()">Refresh</button>
              <button id="runtimeButton" class="secondary" onclick="loadModelRuntime()">Model runtime</button>
              <button id="eventsButton" class="secondary" onclick="loadEvents()">Recent events</button>
              <button id="memoryButton" class="secondary" onclick="loadMemory()">Memory</button>
              <button id="qqStatusButton" class="secondary" onclick="loadQQStatus()">OneBot status</button>
            </div>
          </section>

          <section>
            <h2>Quick State</h2>
            <div class="metric-grid">
              <div class="metric"><span class="label">Model profile</span><span id="metricModel" class="value">unknown</span></div>
              <div class="metric"><span class="label">OneBot ready</span><span id="metricQQ" class="value">unknown</span></div>
              <div class="metric"><span class="label">API usage</span><span id="metricApiUsage" class="value">unknown</span></div>
              <div class="metric"><span class="label">Loop stage</span><span id="metricLoop" class="value">unknown</span></div>
              <div class="metric"><span class="label">Latest decision</span><span id="metricDecision" class="value">none</span></div>
            </div>
          </section>

          <section>
            <h2>Public Remote Debug</h2>
            <p>Starts a local Basic Auth proxy and exposes it through Cloudflare Tunnel when cloudflared is available.</p>
            <div class="actions">
              <button id="remoteDebugStartButton" class="danger" onclick="remoteDebugStart()">Expose debug UI</button>
              <button id="remoteDebugStopButton" class="secondary" onclick="remoteDebugStop()">Stop public debug</button>
              <button id="remoteDebugStatusButton" class="secondary" onclick="remoteDebugStatus()">Remote debug status</button>
            </div>
            <div class="credential-grid">
              <div class="credential"><strong>URL</strong><br><span id="remoteDebugUrl">not running</span></div>
              <div class="credential"><strong>User</strong><br><span id="remoteDebugUser">-</span></div>
              <div class="credential"><strong>Password</strong><br><span id="remoteDebugPassword">-</span></div>
              <div class="credential"><strong>Status</strong><br><span id="remoteDebugState">unknown</span></div>
            </div>
            <div id="remoteDebugSummary" class="summary-box activity">Remote debug is not loaded.</div>
          </section>
        </div>

        <div id="panel-chat" class="tab-panel" role="tabpanel" aria-labelledby="tab-chat">
          <section>
            <h2>Current Chat</h2>
            <p>Recent QQ-visible messages and agent decisions. Click a user message to force a reply or preview one.</p>
            <div id="chatTimeline" class="chat-window">Timeline not loaded.</div>
          </section>

          <section>
            <h2>Manual Force Reply</h2>
            <div class="form-grid">
              <div>
                <label for="manualReplySender">Sender</label>
                <input id="manualReplySender" placeholder="Select a chat bubble or type a sender">
              </div>
              <div>
                <label for="manualReplyEvent">Event ID</label>
                <input id="manualReplyEvent" placeholder="optional" readonly>
              </div>
              <div class="wide">
                <label for="manualReplyMessage">Message to answer</label>
                <textarea id="manualReplyMessage" placeholder="Select a chat bubble or paste the message."></textarea>
              </div>
              <div class="wide">
                <label for="manualReplyInstruction">Extra instruction</label>
                <textarea id="manualReplyInstruction" placeholder="Optional debug-only instruction, e.g. answer with current context."></textarea>
              </div>
            </div>
            <label><input id="manualReplySendToQQ" type="checkbox" checked> Send to QQ if generated</label>
            <div class="actions">
              <button id="manualForceReplyButton" class="danger" onclick="manualForceReply()">Force reply selected message</button>
              <button class="secondary" onclick="clearManualReplySelection()">Clear selection</button>
            </div>
          </section>

          <section>
            <h2>Simulate Chat</h2>
            <label for="userName">User</label>
            <input id="userName" value="tester">
            <label for="message">Message</label>
            <textarea id="message">Say one short sentence about the local agent status.</textarea>
            <button id="simulateButton" onclick="simulateChat()">Run simulate</button>
          </section>

          <section>
            <h2>Manual Spontaneous Topic</h2>
            <p>Creates a local spontaneous reply candidate with thinking level 3. It does not send to QQ by itself.</p>
            <label for="spontaneousContext">Spontaneous context</label>
            <textarea id="spontaneousContext" placeholder="Optional extra context for the manual spontaneous topic."></textarea>
            <button id="spontaneousButton" onclick="triggerSpontaneous()">Spontaneous topic</button>
          </section>
        </div>

        <div id="panel-debug-chat" class="tab-panel" role="tabpanel" aria-labelledby="tab-debug-chat">
          <section>
            <h2>Debug Chat Instance</h2>
            <p>One-on-one chat for debugging the active bot. It reads current persona and memory, but does not write main memory or touch the QQ loop.</p>
            <div class="actions">
              <button id="debugChatStartButton" onclick="debugChatStart()">Start debug chat</button>
              <button id="debugChatStopButton" class="secondary" onclick="debugChatStop()">Stop and clear session</button>
              <button id="debugChatStatusButton" class="secondary" onclick="debugChatStatus()">Debug chat status</button>
            </div>
            <div id="debugChatStatusBox" class="summary-box activity">Debug chat is not loaded.</div>
          </section>

          <section>
            <h2>Live Chat</h2>
            <div id="debugChatTranscript" class="chat-window">Start the debug chat instance first.</div>
            <div class="debug-chat-controls">
              <div>
                <label for="debugChatUser">User name</label>
                <input id="debugChatUser" value="debugger">
              </div>
              <div>
                <label for="debugChatMaxTokens">Max tokens</label>
                <input id="debugChatMaxTokens" type="number" min="1" max="2048" value="700">
              </div>
              <div class="wide">
                <label for="debugChatMessage">Message</label>
                <textarea id="debugChatMessage" placeholder="Talk to the bot without touching QQ or memory."></textarea>
              </div>
            </div>
            <button id="debugChatSendButton" onclick="debugChatSend()">Send debug message</button>
          </section>

          <section>
            <h2>Last Debug Result</h2>
            <div id="debugChatMetrics" class="summary-box activity">No debug chat result yet.</div>
          </section>
        </div>

        <div id="panel-qq" class="tab-panel" role="tabpanel" aria-labelledby="tab-qq">
          <section>
            <h2>NapCat / OneBot</h2>
            <p>NapCat connects to this service through reverse WebSocket. No QQ window automation is used.</p>
            <div class="actions">
              <button id="qqStatusButtonPanel" onclick="loadQQStatus()">Connection status</button>
              <button id="onebotGroupsButton" class="secondary" onclick="loadOneBotGroups()">List groups</button>
              <button id="onebotEventsButton" class="secondary" onclick="loadOneBotEvents()">Recent events</button>
            </div>
            <label for="onebotGroupId">Target group ID</label>
            <input id="onebotGroupId" placeholder="Select an ID returned by List groups">
            <button id="onebotSelectGroupButton" class="secondary" onclick="selectOneBotGroup()">Select group</button>
            <label for="qqText">Test message</label>
            <textarea id="qqText">dry run test message</textarea>
            <button id="qqSendButton" class="danger" onclick="qqSend()">Send through OneBot</button>
          </section>

          <section>
            <h2>Agent Loop</h2>
            <p>Consumes OneBot events, batches consecutive turns, and processes them in order.</p>
            <div class="actions">
              <button id="loopStartButton" onclick="loopStart()">Loop on</button>
              <button id="loopStopButton" class="danger" onclick="loopStop()">Loop off</button>
              <button id="loopTickButton" class="secondary" onclick="loopTick()">Tick once</button>
              <button id="loopScrollbackButton" class="secondary" onclick="loopCollectScrollback()">Collect scrollback</button>
              <button id="loopStatusButton" class="secondary" onclick="loopStatus()">Loop status</button>
            </div>
            <div id="loopActivity" class="summary-box activity">Loop activity not loaded.</div>
            <h3>Queue</h3>
            <div id="queueInspector" class="summary-box activity">Queue not loaded.</div>
            <h3>LLM Now</h3>
            <div id="llmTrace" class="summary-box activity">No active model work.</div>
          </section>
        </div>

        <div id="panel-provider" class="tab-panel" role="tabpanel" aria-labelledby="tab-provider">
          <section>
            <h2>Provider Runtime</h2>
            <p>Qwen persona mode is the default local production path. Legacy raw Qwen is only for model diagnostics; hybrid Grok keeps the API final-reply route available.</p>
            <label for="providerSelect">Active provider</label>
            <select id="providerSelect">
              <option value="unloaded">unloaded</option>
              <option value="local_raw">legacy raw qwen: no persona/context</option>
              <option value="qwen">qwen: persona + long context</option>
              <option value="hybrid">hybrid grok: qwen local + API final</option>
              <option value="local">legacy local</option>
              <option value="grok">grok</option>
            </select>
            <div class="actions">
              <button id="providerStatusButton" class="secondary" onclick="loadProviderStatus()">Provider status</button>
              <button id="providerSwitchButton" class="danger" onclick="switchProvider()">Switch provider</button>
              <button class="secondary" onclick="switchProviderTo('qwen')">Qwen persona ON</button>
              <button class="secondary" onclick="switchProviderTo('local_raw')">Legacy raw Qwen</button>
              <button class="secondary" onclick="switchProviderTo('hybrid')">Hybrid Grok ON</button>
              <button id="providerTestButton" onclick="testProvider()">Test provider</button>
              <button id="providerSoakButton" class="secondary" onclick="runProviderSoak()">Run duplicate soak</button>
            </div>
            <label for="providerTestMessage">Provider test message</label>
            <textarea id="providerTestMessage">Return a short JSON health check.</textarea>
          </section>

          <section>
            <h2>xAI API Key</h2>
            <p>The key is saved to .env. The UI and logs only show masked status.</p>
            <label for="xaiApiKey">XAI_API_KEY</label>
            <input id="xaiApiKey" type="password" placeholder="xai-...">
            <button id="providerKeyButton" class="danger" onclick="saveProviderKey()">Save API key</button>
          </section>

          <section>
            <h2>Budget / Trace</h2>
            <h3>API Usage</h3>
            <div id="apiUsageSummary" class="summary-box activity">API usage not loaded.</div>
            <h3>Provider Status</h3>
            <div id="providerSummary" class="summary-box activity">Provider status not loaded.</div>
            <div class="actions">
              <button class="secondary" onclick="loadProviderTraces()">Recent traces</button>
              <button class="secondary" onclick="loadLatestProviderTrace()">Latest full trace</button>
            </div>
          </section>
        </div>

        <div id="panel-model" class="tab-panel" role="tabpanel" aria-labelledby="tab-model">
          <section>
            <h2>Model Profiles</h2>
            <p>Switching stops the loop, reloads the selected model, rebuilds the agent, and keeps the active personality memory database.</p>
            <label for="modelProfile">Model profile</label>
            <select id="modelProfile"></select>
            <div class="actions">
              <button id="modelProfilesButton" class="secondary" onclick="loadModelProfiles()">Load profiles</button>
              <button id="modelSwitchButton" class="danger" onclick="switchModel()">Switch model</button>
              <button id="modelStopLocalButton" class="danger" onclick="stopLocalModel()">Stop local model</button>
              <button class="secondary" onclick="loadModelRuntime()">Model runtime</button>
            </div>
          </section>

          <section>
            <h2>Model Smoke Test</h2>
            <label for="modelSmokeMessage">Smoke test message</label>
            <textarea id="modelSmokeMessage">用一句话说明当前本地模型是否能回复。</textarea>
            <button id="modelSmokeButton" onclick="modelSmoke()">Run model smoke</button>
          </section>

          <section>
            <h2>Raw Local Chat</h2>
            <p>Calls the local OpenAI-compatible endpoint with one user message only. No persona, memory, web, gate, or custom system prompt is added.</p>
            <label for="rawLocalMessage">Message</label>
            <textarea id="rawLocalMessage">你好，直接用模型本身的能力随便聊两句。</textarea>
            <div class="form-grid compact-grid">
              <div>
                <label for="rawLocalMaxTokens">Max new tokens</label>
                <input id="rawLocalMaxTokens" type="number" min="1" max="4096" value="512">
              </div>
              <div>
                <label for="rawLocalTemperature">Temperature</label>
                <input id="rawLocalTemperature" type="number" min="0" max="2" step="0.05" value="0.7">
              </div>
              <div>
                <label for="rawLocalTopP">Top P</label>
                <input id="rawLocalTopP" type="number" min="0" max="1" step="0.05" value="0.9">
              </div>
            </div>
            <label for="rawLocalStop">Stop sequences, one per line</label>
            <textarea id="rawLocalStop" class="compact-textarea"></textarea>
            <div class="actions">
              <button id="rawLocalChatButton" onclick="rawLocalChat()">Run raw local chat</button>
              <button class="secondary" onclick="switchProviderTo('local_raw')">Use legacy raw Qwen in QQ loop</button>
              <button class="secondary" onclick="switchProviderTo('qwen')">Use Qwen persona in QQ loop</button>
            </div>
          </section>

          <section>
            <h2>Offload Benchmark</h2>
            <p>Temporarily restarts the model server across current IQ2M GPU/RAM profiles, records speed and memory snapshots, then restores the active model profile.</p>
            <label for="offloadProfiles">Profiles</label>
            <textarea id="offloadProfiles">qwen3-30b-iq2m-full-gpu
qwen3-30b-iq2m-hybrid-high
qwen3-30b-iq2m-hybrid-medium
qwen3-30b-iq2m-cpu-ram</textarea>
            <button id="offloadBenchmarkButton" class="danger" onclick="runOffloadBenchmark()">Run offload benchmark</button>
          </section>
        </div>

        <div id="panel-settings" class="tab-panel" role="tabpanel" aria-labelledby="tab-settings">
          <section>
            <h2>Runtime Settings</h2>
            <label for="thinkLevel">Default thinking</label>
            <select id="thinkLevel">
              <option value="0">0 automatic</option>
              <option value="1">1 lowest</option>
              <option value="2">2 medium</option>
              <option value="3">3 high</option>
            </select>
            <label for="activityLevel">Activity <span id="activityValue" class="inline-value">0.35</span></label>
            <input id="activityLevel" type="range" min="0" max="1" step="0.05" value="0.35" oninput="updateSettingLabels()">
            <label for="debugMode">Debug mode</label>
            <select id="debugMode">
              <option value="0">0 default: reply policy for all users</option>
              <option value="1">1 target only: show no-reply reasons</option>
            </select>
            <div class="actions">
              <button id="settingsApplyButton" onclick="applyAgentSettings()">Apply settings</button>
              <button id="settingsLoadButton" class="secondary" onclick="loadAgentSettings()">Load settings</button>
              <button id="settingsSpontaneousButton" class="secondary" onclick="triggerSpontaneousFromSettings()">Manual spontaneous topic</button>
            </div>
          </section>

          <section>
            <h2>Social State</h2>
            <p>Users are detected from QQ-visible senders and interaction memory. Manual input remains as a fallback.</p>
            <div class="form-grid">
              <div>
                <label for="socialUserList">Detected users</label>
                <select id="socialUserList" size="7" onchange="selectSocialUser(this.value)"></select>
              </div>
              <div>
                <label for="socialUserName">Selected / manual user</label>
                <input id="socialUserName" value="tester" onchange="loadSocialProfile()">
                <div class="actions tight-actions">
                  <button id="socialUsersButton" class="secondary" onclick="loadSocialUsers()">Refresh users</button>
                  <button id="socialLoadButton" class="secondary" onclick="loadSocialState()">Load user</button>
                </div>
              </div>
              <div>
                <label for="affinityLevel">User affinity <span id="affinityValue" class="inline-value">0.50</span></label>
                <input id="affinityLevel" type="range" min="0" max="1" step="0.05" value="0.5" oninput="updateSocialLabels()">
              </div>
              <div>
                <label for="userLanguagePreference">Language preference</label>
                <input id="userLanguagePreference" placeholder="auto / zh-CN / en / mixed">
              </div>
              <div>
                <label for="userTonePreference">Tone preference</label>
                <input id="userTonePreference" placeholder="compact notes for this user">
              </div>
              <div>
                <label for="userAliases">Aliases</label>
                <input id="userAliases" placeholder="comma separated">
              </div>
              <div class="wide">
                <label for="userRelationshipNotes">Relationship notes</label>
                <textarea id="userRelationshipNotes" placeholder="Short runtime notes for this user"></textarea>
              </div>
              <div class="wide">
                <label for="socialNote">Override note</label>
                <input id="socialNote" value="debug UI override">
              </div>
              <div class="wide">
                <pre id="socialProfileDetails">No user profile loaded.</pre>
              </div>
            </div>
            <div class="actions">
              <button id="socialApplyButton" onclick="applySocialState()">Save user profile</button>
              <button id="socialChangesButton" class="secondary" onclick="loadSocialChanges()">Recent social changes</button>
            </div>
          </section>

          <section>
            <h2>Global Social</h2>
            <div class="form-grid">
              <div>
                <label for="globalMood">Global mood</label>
                <input id="globalMood" value="">
              </div>
              <div>
                <label for="moodIntensity">Mood intensity <span id="moodIntensityValue" class="inline-value">0.00</span></label>
                <input id="moodIntensity" type="range" min="0" max="1" step="0.05" value="0" oninput="updateSocialLabels()">
              </div>
              <div>
                <label for="globalAffinity">Global affinity <span id="globalAffinityValue" class="inline-value">0.50</span></label>
                <input id="globalAffinity" type="range" min="0" max="1" step="0.05" value="0.5" oninput="updateSocialLabels()">
              </div>
              <div class="wide">
                <label for="globalSocialNote">Global note</label>
                <input id="globalSocialNote" value="debug UI global override">
              </div>
            </div>
            <div class="actions">
              <button id="socialGlobalApplyButton" onclick="applyGlobalSocialState()">Save global social</button>
              <button id="socialGlobalLoadButton" class="secondary" onclick="loadGlobalSocialState()">Load global social</button>
            </div>
          </section>
        </div>

        <div id="panel-memory" class="tab-panel" role="tabpanel" aria-labelledby="tab-memory">
          <section>
            <h2>Memory Search</h2>
            <label for="memorySearchQuery">Search query</label>
            <input id="memorySearchQuery" placeholder="Find long-term memories">
            <div class="actions">
              <button id="memorySearchButton" onclick="searchMemory()">Search memory</button>
              <button id="memoryRefreshButton" class="secondary" onclick="loadMemory()">Refresh memory</button>
            </div>
          </section>

          <section>
            <h2>Memory Editor</h2>
            <p>Long-term memories are saved in the active personality SQLite store. Short-term context is appended as an event.</p>
            <div class="form-grid">
              <div>
                <label for="memoryId">Long-term memory ID</label>
                <input id="memoryId" placeholder="Blank creates a new memory">
              </div>
              <div>
                <label for="memoryKind">Long-term kind</label>
                <select id="memoryKind">
                  <option value="working_context">working_context</option>
                  <option value="relationship">relationship</option>
                  <option value="preference">preference</option>
                  <option value="taboo">taboo</option>
                  <option value="episode">episode</option>
                  <option value="procedural">procedural</option>
                  <option value="behavior_feedback">behavior_feedback</option>
                  <option value="profile">profile</option>
                </select>
              </div>
              <div class="wide">
                <label for="memoryConfidence">Confidence <span id="memoryConfidenceValue" class="inline-value">0.70</span></label>
                <input id="memoryConfidence" type="range" min="0" max="1" step="0.05" value="0.7" oninput="updateMemoryLabels()">
              </div>
              <div class="wide">
                <label for="memorySummary">Long-term summary</label>
                <textarea id="memorySummary" placeholder="Stable fact, preference, relationship note, taboo, or working context."></textarea>
              </div>
              <div class="wide">
                <label for="memoryMetadata">Metadata JSON</label>
                <textarea id="memoryMetadata">{}</textarea>
              </div>
            </div>
            <div class="actions">
              <button id="memorySaveButton" onclick="saveMemory()">Save memory</button>
              <button id="memoryDeleteButton" class="danger" onclick="deleteMemory()">Delete memory</button>
            </div>
            <label for="memoryDeleteQuery">Delete query</label>
            <input id="memoryDeleteQuery" placeholder="Used when ID is blank">
            <label for="shortTermContent">Short-term context event</label>
            <textarea id="shortTermContent" placeholder="Temporary context/event to add to the recent log."></textarea>
            <div class="actions">
              <button id="shortTermSaveButton" onclick="saveShortTerm()">Save short-term</button>
            </div>
          </section>
        </div>

        <div id="panel-web" class="tab-panel" role="tabpanel" aria-labelledby="tab-web">
          <section>
            <h2>Search</h2>
            <label for="query">Query</label>
            <input id="query" value="Qwen3 GGUF llama.cpp">
            <button id="searchButton" onclick="webSearch()">Search</button>
          </section>

          <section>
            <h2>Read URL</h2>
            <p>Uses the configured browser reader and allowlist. Failed reads show the backend reason in Output.</p>
            <label for="webReadUrl">URL</label>
            <input id="webReadUrl" placeholder="https://en.wikipedia.org/wiki/...">
            <button id="webReadButton" onclick="webRead()">Read URL</button>
          </section>
        </div>

        <div id="panel-logs" class="tab-panel" role="tabpanel" aria-labelledby="tab-logs">
          <section>
            <h2>Raw Logs</h2>
            <p>The pinned console stays visible on desktop. This tab gives the same raw areas more room when you need to inspect an event id.</p>
            <div class="actions">
              <button id="timelineButton" class="secondary" onclick="loadTimeline()">Timeline</button>
              <button class="secondary" onclick="loadEvents()">Recent events</button>
              <button class="secondary" onclick="loadStatus()">Status</button>
              <button class="secondary" onclick="loopStatus()">Loop status</button>
              <button class="secondary" onclick="loadMemory()">Memory</button>
            </div>
          </section>

          <section class="danger-zone">
            <h2>Service Control</h2>
            <p>Reboot is an agent service action. It should be used when persona files or runtime wiring need to be reloaded.</p>
            <button id="styleBundleExportButton" class="secondary" onclick="exportStyleBundle()">Export style bundle</button>
            <button id="styleAnchorRefreshButton" class="secondary" onclick="refreshStyleAnchor()">Refresh style anchor</button>
            <button id="agentRebootButton" class="danger" onclick="agentReboot()">Restart agent service</button>
            <button id="fullRestartButton" class="danger" onclick="fullRestart()">Full service restart</button>
          </section>
        </div>
      </div>

      <aside class="console" aria-label="Pinned debug console">
        <div class="console-card">
          <h2>Result Summary</h2>
          <div id="summary" class="summary-box">No action yet.</div>
        </div>
        <div class="console-card">
          <h2>LLM Now</h2>
          <div id="consoleLlmNow" class="summary-box">No active model work.</div>
        </div>
        <div class="console-card">
          <h2>Output</h2>
          <pre id="output"></pre>
        </div>
        <div class="console-card">
          <h2>Status JSON</h2>
          <pre id="status"></pre>
        </div>
        <div class="console-card">
          <h2>Memory</h2>
          <pre id="memory"></pre>
        </div>
      </aside>
    </div>
  </main>

  <script>
    async function requestJson(url, options) {
      const response = await fetch(url, options || {});
      const text = await response.text();
      let body = text;
      try { body = JSON.parse(text); } catch (_) {}
      if (!response.ok) {
        throw new Error(JSON.stringify(body, null, 2));
      }
      return body;
    }

    const outputEntries = new Map();
    let outputSequence = 0;
    let lastLoopActivityKey = "";
    let cachedStatus = null;
    let cachedLoopStatus = null;
    let latestLoopStatus = null;
    let latestTimelineItems = [];
    let selectedTimelineItem = null;
    let latestDebugChatStatus = null;
    let latestRemoteDebugStatus = null;
    const maxOutputEntries = 60;

    function activateTab(name) {
      for (const panel of document.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("active", panel.id === `panel-${name}`);
      }
      for (const button of document.querySelectorAll(".tab-button")) {
        button.setAttribute("aria-selected", String(button.id === `tab-${name}`));
      }
      window.localStorage.setItem("debug-active-tab", name);
    }

    function show(id, value) {
      const element = document.getElementById(id);
      element.textContent = JSON.stringify(compactPayload(value), null, 2);
      scrollToBottom(element);
    }

    function showOutput(value, key) {
      showMemory(extractMemoryPayload(value));
      appendOutput(value, key);
    }

    function appendOutput(value, key) {
      const entryKey = key || `${Date.now()}-${outputSequence++}`;
      const timestamp = new Date().toLocaleTimeString();
      outputEntries.set(entryKey, {
        timestamp,
        value: compactPayload(withoutMemoryPayload(value))
      });
      while (outputEntries.size > maxOutputEntries) {
        outputEntries.delete(outputEntries.keys().next().value);
      }
      renderOutputLog();
    }

    function renderOutputLog() {
      const blocks = [];
      for (const entry of outputEntries.values()) {
        blocks.push(formatOutputEntry(entry));
      }
      const element = document.getElementById("output");
      element.textContent = blocks.join("\\n\\n");
      scrollToBottom(element);
    }

    function formatOutputEntry(entry) {
      const value = entry.value || {};
      const operation = value.operation || "log";
      const state = value.state || "snapshot";
      const elapsed = value.elapsed_seconds !== undefined ? ` elapsed=${value.elapsed_seconds}s` : "";
      const lines = [`=== ${entry.timestamp} ${operation} ${state}${elapsed} ===`];
      lines.push(...summarizeOutputPayload(value));
      return lines.filter((line) => line !== null && line !== undefined && line !== "").join("\\n");
    }

    function summarizeOutputPayload(value) {
      if (!value || typeof value !== "object") {
        return [String(value ?? "")];
      }
      if (value.state === "running") {
        return [`${value.operation || "operation"} running... ${value.elapsed_seconds ?? "?"}s`];
      }
      if (value.state === "error") {
        return [`error: ${shortLine(value.error || "unknown")}`];
      }

      const operation = value.operation || "";
      const result = value.result !== undefined ? value.result : value;
      if (operation.startsWith("loop_") || result?.recent_decisions || result?.activity) {
        return summarizeLoopOutput(result);
      }
      if (operation === "events" || Array.isArray(result?.events) || Array.isArray(result)) {
        return summarizeEventsOutput(result);
      }
      if (operation === "debug_timeline" || Array.isArray(result?.items)) {
        return summarizeTimelineOutput(result);
      }
      if (result?.action !== undefined && (result?.reply !== undefined || result?.reason !== undefined)) {
        return summarizeAgentResult(result);
      }
      if (operation === "qq_read") {
        return summarizeQqRead(result);
      }
      if (operation === "qq_send") {
        return summarizeQqSend(result);
      }
      if (operation === "provider_status" || operation === "provider_switch" || operation === "provider_key") {
        return summarizeProviderOutput(result);
      }
      if (operation.startsWith("debug_chat")) {
        return summarizeDebugChatOutput(result);
      }
      if (operation.startsWith("remote_debug")) {
        return summarizeRemoteDebugOutput(result);
      }
      return summarizeGenericOutput(operation, result);
    }

    function summarizeLoopOutput(result) {
      const activity = result?.activity || {};
      const recent = result?.recent_decisions || result?.handled || [];
      const latest = recent.length ? recent[recent.length - 1] : null;
      const lines = [
        `loop: running=${result?.running ?? "?"} stage=${activity.stage || "unknown"}`,
        `queue: aggregating=${result?.aggregating_message_count ?? 0} pending=${result?.pending_message_count ?? 0} queued=${result?.queued_message_count ?? 0} inflight=${result?.inflight_message_count ?? 0}`,
      ];
      if (activity.sender_name || activity.message_text) {
        lines.push(`active: ${activity.sender_name || "unknown"}: ${shortLine(activity.message_text || "")}`);
      }
      if (activity.detail) {
        lines.push(`detail: ${shortLine(activity.detail)}`);
      }
      if (latest) {
        lines.push("latest decision:");
        lines.push(...summarizeDecision(latest).map((line) => `  ${line}`));
      } else if (result?.reason) {
        lines.push(`reason: ${shortLine(result.reason)}`);
      }
      return lines;
    }

    function summarizeDecision(decision) {
      const metadata = decision.metadata || {};
      const lines = [
        `from: ${decision.sender_name || "unknown"}`,
        `msg: ${shortLine(decision.message_text || "")}`,
        `decision: ${decision.action || "?"} reason=${shortLine(decision.reason || "")}`,
        `send: ${decision.sent ?? false} ${decision.send_reason || ""}`.trim(),
      ];
      const reply = metadata.cleaned_reply || metadata.agent_reply || "";
      if (reply) {
        lines.push(`reply: ${shortLine(reply)}`);
      }
      const tokenLine = formatTokenLine(metadata);
      if (tokenLine) {
        lines.push(tokenLine);
      }
      if (metadata.web_used !== undefined || metadata.search_used !== undefined || metadata.web_query) {
        lines.push(`web: used=${metadata.web_used ?? false} search=${metadata.search_used ?? false} query=${shortLine(metadata.web_query || "")}`);
      }
      if (metadata.interaction_plan) {
        lines.push(formatInteractionLine(metadata.interaction_plan));
      }
      if (metadata.quality_review) {
        lines.push(formatQualityLine(metadata));
      }
      if (metadata.message_identity) {
        lines.push(`turn: ${shortLine(metadata.message_identity)}`);
      }
      if (metadata.provider_trace_id) {
        lines.push(`trace: ${metadata.provider_trace_id}`);
      }
      return lines;
    }

    function summarizeAgentResult(result) {
      const metadata = result.metadata || {};
      const lines = [
        `decision: ${result.action || "?"} reason=${shortLine(result.reason || "")}`,
        `sent: ${result.sent ?? "n/a"}`,
      ];
      const reply = result.reply || metadata.agent_reply || metadata.cleaned_reply || "";
      if (reply) {
        lines.push(`reply: ${shortLine(reply)}`);
      }
      const tokenLine = formatTokenLine(metadata);
      if (tokenLine) {
        lines.push(tokenLine);
      }
      if (metadata.web_used !== undefined || metadata.search_used !== undefined || metadata.web_query) {
        lines.push(`web: used=${metadata.web_used ?? false} search=${metadata.search_used ?? false} query=${shortLine(metadata.web_query || "")}`);
      }
      if (metadata.interaction_plan) {
        lines.push(formatInteractionLine(metadata.interaction_plan));
      }
      if (metadata.quality_review) {
        lines.push(formatQualityLine(metadata));
      }
      if (metadata.provider_trace_id) {
        lines.push(`trace: ${metadata.provider_trace_id}`);
      }
      return lines;
    }

    function formatInteractionLine(plan) {
      if (!plan) {
        return "";
      }
      return `interaction: ${plan.mode || "unknown"} hook=${plan.hook_budget ?? "?"} affinity=${plan.affinity ?? "?"} kind=${plan.message_kind || "?"}`;
    }

    function formatQualityLine(metadata) {
      const review = metadata.quality_review || {};
      const hits = Array.isArray(review.rule_hits) ? review.rule_hits.join(",") : (review.rule_hits || "");
      const rewrite = metadata.quality_rewrite_used ? ` rewrite=${shortLine(metadata.quality_rewrite_reply || "")}` : "";
      return `quality: score=${review.score ?? "?"} rewrite=${review.rewrite_needed ?? false} hits=${hits}${rewrite}`;
    }

    function summarizeEventsOutput(result) {
      const events = Array.isArray(result) ? result : (result?.events || result?.recent_events || []);
      if (!Array.isArray(events) || !events.length) {
        return ["events: none"];
      }
      return events.slice(-12).map((event) => {
        const time = event.created_at || event.timestamp || "";
        const source = event.source || "";
        const kind = event.kind || "";
        const content = event.content || event.message || "";
        return `${time} ${source} ${kind}: ${shortLine(content)}`.trim();
      });
    }

    function summarizeTimelineOutput(result) {
      const items = Array.isArray(result?.items) ? result.items : [];
      if (!items.length) {
        return ["timeline: no visible debug events"];
      }
      return items.slice(-30).map((item) => formatTimelineItem(item));
    }

    function renderChatTimeline(items) {
      latestTimelineItems = Array.isArray(items) ? items : [];
      const element = document.getElementById("chatTimeline");
      if (!element) {
        return;
      }
      if (!latestTimelineItems.length) {
        element.textContent = "No chat events yet.";
        return;
      }
      const visible = latestTimelineItems.slice(-80);
      const offset = latestTimelineItems.length - visible.length;
      const blocks = visible.map((item, index) => chatBubbleHtml(item, offset + index));
      element.innerHTML = blocks.join("");
      scrollToBottom(element);
    }

    function chatBubbleHtml(item, index) {
      const kind = item.kind || "";
      const selectable = kind === "group_message" && item.message;
      const isAgent = kind === "assistant_reply" || kind === "assistant_placeholder";
      const isDecision = kind === "loop_decision" || kind === "assistant_blocked";
      const selected = selectedTimelineItem && selectedTimelineItem.event_id === item.event_id;
      const classes = ["chat-bubble"];
      if (isAgent) classes.push("agent");
      if (isDecision) classes.push("decision");
      if (selected) classes.push("selected");
      const onclick = selectable ? ` onclick="selectTimelineItem(${index})"` : "";
      const label = isAgent ? "bot" : (item.who || "unknown");
      const text = item.reply || item.message || item.reason || "";
      const details = Array.isArray(item.summary_lines) ? item.summary_lines.slice(1, 4) : [];
      const detailHtml = details.length
        ? `<div class="chat-detail">${details.map((line) => escapeHtml(shortLine(line, 180))).join("<br>")}</div>`
        : "";
      const decision = item.decision && kind !== "group_message" ? ` · ${escapeHtml(item.decision)}` : "";
      return `
        <button class="${classes.join(" ")}" type="button"${onclick}>
          <div class="chat-meta"><span>${escapeHtml(shortTime(item.time))} · #${item.event_id} · ${escapeHtml(label)}${decision}</span><span>${item.sent === true ? "sent" : ""}</span></div>
          <div class="chat-text">${escapeHtml(text || "(empty)")}</div>
          ${detailHtml}
        </button>
      `;
    }

    function selectTimelineItem(index) {
      const item = latestTimelineItems[index];
      if (!item || !item.message) {
        return;
      }
      selectedTimelineItem = item;
      document.getElementById("manualReplySender").value = item.who || "";
      document.getElementById("manualReplyMessage").value = item.message || "";
      document.getElementById("manualReplyEvent").value = item.event_id || "";
      renderChatTimeline(latestTimelineItems);
    }

    function clearManualReplySelection() {
      selectedTimelineItem = null;
      document.getElementById("manualReplySender").value = "";
      document.getElementById("manualReplyMessage").value = "";
      document.getElementById("manualReplyEvent").value = "";
      document.getElementById("manualReplyInstruction").value = "";
      renderChatTimeline(latestTimelineItems);
    }

    function renderDebugChatStatus(status) {
      latestDebugChatStatus = status || null;
      const transcript = Array.isArray(status?.transcript) ? status.transcript : [];
      const statusLines = [
        `enabled: ${status?.enabled ?? false}`,
        `session: ${status?.session_id || ""}`,
        `messages: ${status?.message_count ?? transcript.length}`,
        `log: ${status?.log_path || ""}`,
      ];
      document.getElementById("debugChatStatusBox").textContent = statusLines.join("\\n");
      renderDebugChatTranscript(transcript);
      renderDebugChatMetrics(status?.latest_result || null);
    }

    function renderDebugChatTranscript(transcript) {
      const element = document.getElementById("debugChatTranscript");
      if (!element) {
        return;
      }
      if (!Array.isArray(transcript) || !transcript.length) {
        element.textContent = latestDebugChatStatus?.enabled ? "No debug chat messages yet." : "Start the debug chat instance first.";
        return;
      }
      element.innerHTML = transcript.map((turn) => {
        const classes = ["chat-bubble"];
        if (turn.role === "assistant") {
          classes.push("agent");
        }
        return `
          <div class="${classes.join(" ")}">
            <div class="chat-meta"><span>${escapeHtml(shortTime(turn.created_at))} 路 ${escapeHtml(turn.role || "")}</span></div>
            <div class="chat-text">${escapeHtml(turn.content || "")}</div>
          </div>
        `;
      }).join("");
      scrollToBottom(element);
    }

    function renderDebugChatMetrics(result) {
      const element = document.getElementById("debugChatMetrics");
      if (!element) {
        return;
      }
      if (!result) {
        element.textContent = "No debug chat result yet.";
        return;
      }
      const usage = result.usage || {};
      const tps = result.tokens_per_second || {};
      const lines = [
        `reply: ${result.reply || ""}`,
        `would_reply: ${result.would_reply ?? "?"}`,
        `reason: ${result.debug_reason || ""}`,
        `parse: ${result.parse_status || ""}`,
        `model: ${result.model || ""}`,
        `elapsed: ${result.elapsed_seconds ?? "?"}s, latency: ${result.latency_seconds ?? "?"}s`,
        `tokens: prompt=${usage.prompt_tokens ?? usage.input_tokens ?? "?"}, completion=${usage.completion_tokens ?? usage.output_tokens ?? "?"}, total=${usage.total_tokens ?? "?"}`,
        `tok/s: prompt=${tps.prompt_tokens ?? tps.input_tokens ?? "?"}, completion=${tps.completion_tokens ?? tps.output_tokens ?? "?"}, total=${tps.total_tokens ?? "?"}`,
        `rewrite: ${result.rewrite?.used ?? false} ${result.rewrite?.reason || ""}`,
        `memory read: ${result.memory?.count ?? 0} lines`,
      ];
      element.textContent = lines.join("\\n");
      scrollToBottom(element);
    }

    function renderRemoteDebugStatus(status) {
      latestRemoteDebugStatus = status || null;
      document.getElementById("remoteDebugUrl").textContent = status?.public_url || "not running";
      document.getElementById("remoteDebugUser").textContent = status?.username || "-";
      document.getElementById("remoteDebugPassword").textContent = status?.password || "-";
      document.getElementById("remoteDebugState").textContent = status?.running ? "running" : (status?.error || "stopped");
      const lines = [
        `running: ${status?.running ?? false}`,
        `proxy: ${status?.proxy_running ?? false} ${status?.local_proxy_url || ""}`,
        `tunnel: ${status?.tunnel_running ?? false}`,
        `public: ${status?.public_url || ""}`,
        `user: ${status?.username || ""}`,
        `password: ${status?.password || ""}`,
        `cloudflared: ${status?.cloudflared || ""}`,
        `error: ${status?.error || "none"}`,
      ];
      document.getElementById("remoteDebugSummary").textContent = lines.join("\\n");
    }

    function formatTimelineItem(item) {
      if (Array.isArray(item.summary_lines) && item.summary_lines.length) {
        return item.summary_lines.map((line) => shortLine(line, 240)).join("\\n");
      }
      if (item.summary) {
        return shortLine(item.summary, 320);
      }
      const time = shortTime(item.time);
      const who = item.who || "unknown";
      const message = item.message ? ` said "${shortLine(item.message, 120)}"` : "";
      const decision = item.decision ? ` -> ${item.decision}` : "";
      const reason = item.reason ? ` (${shortLine(item.reason, 120)})` : "";
      const sent = item.sent === null || item.sent === undefined ? "" : ` sent=${item.sent}`;
      const reply = item.reply ? ` reply="${shortLine(item.reply, 140)}"` : "";
      const tokenLine = formatTimelineTokens(item.tokens || {});
      const web = item.web && item.web.used ? ` web="${shortLine(item.web.query || "", 100)}" sources=${item.web.source_count ?? 0}` : "";
      return `${time} #${item.event_id} ${who}${message}${decision}${reason}${sent}${reply}${tokenLine}${web}`.trim();
    }

    function formatTimelineTokens(tokens) {
      if (!tokens || (tokens.prompt === undefined && tokens.completion === undefined && tokens.total === undefined && !tokens.local && !tokens.api)) {
        return "";
      }
      const local = tokens.local || {};
      const api = tokens.api || {};
      const parts = [];
      if (local.total !== undefined) {
        parts.push(`local=${local.prompt ?? "?"}/${local.completion ?? "?"}/${local.total ?? "?"}`);
      }
      if (api.total !== undefined) {
        parts.push(`api=${api.input ?? "?"}/${api.output ?? "?"}/${api.total ?? "?"}`);
        if (api.cached !== undefined) {
          parts.push(`cached=${api.cached}`);
        }
        if (api.reasoning !== undefined) {
          parts.push(`reasoning=${api.reasoning}`);
        }
      }
      if (!parts.length) {
        parts.push(`${tokens.prompt ?? "?"}/${tokens.completion ?? "?"}/${tokens.total ?? "?"}`);
      }
      parts.push(`latency=${tokens.latency_seconds ?? local.latency_seconds ?? api.latency_seconds ?? "?"}s`);
      return ` tokens ${parts.join(" ")}`;
    }

    function shortTime(value) {
      const text = String(value || "");
      const match = text.match(/T?(\\d{2}:\\d{2}:\\d{2})/);
      return match ? match[1] : text.slice(0, 19);
    }

    function summarizeQqRead(result) {
      return [
        `group: active=${result?.active_group_name || "unknown"} expected=${result?.expected_group_name || "unset"} matched=${result?.group_matched ?? "?"}`,
        `messages: visible=${(result?.visible_items || []).length} target=${(result?.target_messages || []).length}`,
      ];
    }

    function summarizeQqSend(result) {
      if (!result?.sent) {
        return [
          `send blocked: ${result?.reason || "unknown"}`,
          `group: active=${result?.verification?.active_group_name || "unknown"} expected=${result?.verification?.expected_group_name || "unset"}`,
        ];
      }
      return [
        "send: ok",
        `duration: ${result.duration_seconds ?? "?"}s`,
        `group: ${result?.verification?.active_group_name || "unknown"}`,
      ];
    }

    function summarizeProviderOutput(result) {
      const provider = result?.provider || result || {};
      const budget = provider.budget || {};
      const grok = provider.grok || {};
      return [
        `provider: ${provider.active_provider || "unknown"} model=${grok.model || "unknown"}`,
        `api key: ${grok.api_key_configured ? grok.api_key_masked || "configured" : "missing"}`,
        `usage: prompt=${formatInteger(budget.prompt_tokens)} completion=${formatInteger(budget.completion_tokens)} total=${formatInteger(budget.total_tokens)}`,
      ];
    }

    function summarizeDebugChatOutput(result) {
      if (!result || typeof result !== "object") {
        return ["debug chat: no result"];
      }
      const latest = result.latest_result || result;
      const usage = latest.usage || {};
      const tps = latest.tokens_per_second || {};
      const lines = [
        `debug chat: enabled=${result.enabled ?? latest.enabled ?? "?"} session=${result.session_id || latest.session_id || ""}`,
      ];
      if (latest.reply) {
        lines.push(`reply: ${shortLine(latest.reply)}`);
      }
      if (latest.debug_reason) {
        lines.push(`reason: ${shortLine(latest.debug_reason)}`);
      }
      if (latest.model || latest.latency_seconds !== undefined) {
        lines.push(`model: ${latest.model || "unknown"} latency=${latest.latency_seconds ?? "?"}s elapsed=${latest.elapsed_seconds ?? "?"}s`);
      }
      if (Object.keys(usage).length) {
        lines.push(`tokens: prompt=${usage.prompt_tokens ?? usage.input_tokens ?? "?"} completion=${usage.completion_tokens ?? usage.output_tokens ?? "?"} total=${usage.total_tokens ?? "?"} tok/s=${tps.completion_tokens ?? tps.output_tokens ?? "?"}`);
      }
      lines.push(`log: ${latest.log_path || result.log_path || ""}`);
      return lines;
    }

    function summarizeRemoteDebugOutput(result) {
      if (!result || typeof result !== "object") {
        return ["remote debug: no result"];
      }
      return [
        `remote debug: running=${result.running ?? false} proxy=${result.proxy_running ?? false} tunnel=${result.tunnel_running ?? false}`,
        `url: ${result.public_url || "not available"}`,
        `user: ${result.username || "-"}`,
        `password: ${result.password || "-"}`,
        `error: ${result.error || "none"}`,
      ];
    }

    function summarizeGenericOutput(operation, result) {
      if (!result || typeof result !== "object") {
        return [`${operation || "operation"}: ${String(result ?? "done")}`];
      }
      const hidden = new Set(["visible_items", "raw", "metadata", "send_result", "verification"]);
      const keys = Object.keys(result).filter((key) => !hidden.has(key));
      const lines = [`${operation || "operation"} completed.`];
      for (const key of keys.slice(0, 8)) {
        const value = result[key];
        if (value === null || value === undefined || typeof value === "object") {
          continue;
        }
        lines.push(`${key}: ${shortLine(String(value))}`);
      }
      lines.push("raw details: use Logs / Status JSON for full metadata.");
      return lines;
    }

    function formatTokenLine(metadata) {
      if (!metadata) {
        return "";
      }
      const tps = metadata.tokens_per_second || {};
      const prompt = metadata.prompt_tokens ?? metadata.usage?.prompt_tokens;
      const completion = metadata.completion_tokens ?? metadata.usage?.completion_tokens;
      const total = metadata.total_tokens ?? metadata.usage?.total_tokens;
      if (prompt === undefined && completion === undefined && total === undefined) {
        return "";
      }
      return `tokens: prompt=${prompt ?? "?"} completion=${completion ?? "?"} total=${total ?? "?"} tok/s=${tps.completion_tokens ?? "?"}`;
    }

    function shortLine(value, maxLength = 220) {
      const text = String(value ?? "").replace(/\\s+/g, " ").trim();
      if (text.length <= maxLength) {
        return text;
      }
      return `${text.slice(0, maxLength)}...`;
    }

    function showMemory(value) {
      if (value === undefined || value === null) {
        document.getElementById("memory").textContent = "No memory context for this output.";
        return;
      }
      show("memory", value);
    }

    function extractMemoryPayload(value) {
      const metadata = value?.result?.metadata || value?.metadata || null;
      if (metadata?.memory_context) {
        return metadata.memory_context;
      }
      if (metadata?.memory_operation) {
        return metadata.memory_operation;
      }
      if (Array.isArray(value) && value.some((item) => item && item.summary && item.kind)) {
        return value;
      }
      return null;
    }

    function withoutMemoryPayload(value) {
      if (!value || typeof value !== "object") {
        return value;
      }
      const cloned = JSON.parse(JSON.stringify(value));
      const metadata = cloned?.result?.metadata || cloned?.metadata || null;
      if (metadata) {
        delete metadata.memory_lines;
        delete metadata.memory_context;
        delete metadata.memory_operation;
      }
      return cloned;
    }

    function compactPayload(value, depth = 0) {
      if (value === null || value === undefined) {
        return value;
      }
      if (typeof value === "string") {
        return value.length > 1800 ? `${value.slice(0, 1800)}... [truncated ${value.length - 1800} chars]` : value;
      }
      if (typeof value !== "object") {
        return value;
      }
      if (Array.isArray(value)) {
        const items = value.length > 80 ? value.slice(-80) : value;
        return items.map((item) => compactPayload(item, depth + 1));
      }
      if (depth > 5) {
        return "[nested object truncated]";
      }

      const result = {};
      for (const [key, item] of Object.entries(value)) {
        if (key === "memory_context" || key === "memory_lines" || key === "profile_documents") {
          continue;
        }
        if (key === "recent_decisions" && Array.isArray(item)) {
          result[key] = item.slice(-8).map(compactDecision);
          continue;
        }
        if (key === "metadata" && item && typeof item === "object" && !Array.isArray(item)) {
          result[key] = compactMetadata(item);
          continue;
        }
        result[key] = compactPayload(item, depth + 1);
      }
      return result;
    }

    function compactDecision(decision) {
      return {
        created_at: decision.created_at,
        sender_name: decision.sender_name,
        message_text: decision.message_text,
        action: decision.action,
        reason: decision.reason,
        sent: decision.sent,
        send_reason: decision.send_reason,
        elapsed_seconds: decision.elapsed_seconds,
        metadata: compactMetadata(decision.metadata || {})
      };
    }

    function compactMetadata(metadata) {
      const keys = [
        "raw_model_content",
        "cleaned_reply",
        "agent_reply",
        "latency_seconds",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "usage",
        "tokens_per_second",
        "token_usage",
        "engagement_decision",
        "engagement_signals",
        "thinking_level",
        "max_thinking_level",
        "requested_thinking_level",
        "thinking_complexity_level",
        "gate_decision",
        "placeholder_sent",
        "placeholder_text",
        "web_used",
        "local_time_used",
        "search_used",
        "browser_used",
        "web_query",
        "web_sources",
        "web_error",
        "math_used",
        "math_query",
        "math_result",
        "message_identity",
        "source_fingerprint",
        "raw_message_text",
        "loop_turn_cleaning",
        "send_result",
        "stage_timings",
        "provider_decision",
        "provider_trace_id",
        "provider_parse_status",
        "provider_decision_json",
        "interaction_plan",
        "quality_review",
        "quality_second_review",
        "quality_rewrite_used",
        "quality_rewrite_reply",
        "pre_quality_reply"
      ];
      const result = {};
      for (const key of keys) {
        if (metadata[key] !== undefined) {
          result[key] = compactPayload(metadata[key], 1);
        }
      }
      return result;
    }

    function latestFirst(value, key) {
      if (Array.isArray(value)) {
        const items = sortedLatestFirst(value, key);
        return items.map((item) => latestFirst(item, ""));
      }
      if (!value || typeof value !== "object") {
        return value;
      }

      const next = {};
      for (const [childKey, item] of Object.entries(value)) {
        next[childKey] = latestFirst(item, childKey);
      }
      return next;
    }

    function shouldShowLatestFirst(key) {
      return [
        "recent_decisions",
        "handled",
        "events",
        "recent_events",
        "target_messages",
        "visible_items"
      ].includes(key);
    }

    function sortedLatestFirst(items, key) {
      const sortable = items.every((item) => item && typeof item === "object");
      if (!sortable) {
        return items;
      }
      if (items.some((item) => item.id !== undefined)) {
        return [...items].sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
      }
      if (items.some((item) => item.created_at !== undefined)) {
        return [...items].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      }
      if (shouldShowLatestFirst(key)) {
        return [...items].reverse();
      }
      return items;
    }

    function showText(id, value) {
      const element = document.getElementById(id);
      element.textContent = value;
      scrollToBottom(element);
    }

    function scrollToBottom(element) {
      if (!element) {
        return;
      }
      element.scrollTop = element.scrollHeight;
    }

    function elapsedSeconds(startedAt) {
      return Number(((performance.now() - startedAt) / 1000).toFixed(1));
    }

    async function runTimed(operation, buttonId, action) {
      const button = document.getElementById(buttonId);
      const previousLabel = button ? button.textContent : "";
      const startedAt = performance.now();
      let timerId = null;
      const outputKey = `${operation}-${Date.now()}-${outputSequence++}`;

      if (button) {
        button.disabled = true;
        button.textContent = "Running...";
      }

      const tick = () => {
        showText("summary", `${operation} running... ${elapsedSeconds(startedAt)}s`);
        showOutput({
          state: "running",
          operation: operation,
          elapsed_seconds: elapsedSeconds(startedAt)
        }, outputKey);
      };
      tick();
      timerId = window.setInterval(tick, 1000);

      try {
        const result = await action();
        showText("summary", summarizeResult(operation, "done", elapsedSeconds(startedAt), result));
        showOutput({
          state: "done",
          operation: operation,
          elapsed_seconds: elapsedSeconds(startedAt),
          result: result
        }, outputKey);
        await refreshTopStatus();
        return result;
      } catch (error) {
        showText("summary", `${operation} failed after ${elapsedSeconds(startedAt)}s\\n${String(error.message || error)}`);
        showOutput({
          state: "error",
          operation: operation,
          elapsed_seconds: elapsedSeconds(startedAt),
          error: String(error.message || error)
        }, outputKey);
        return null;
      } finally {
        if (timerId !== null) {
          window.clearInterval(timerId);
        }
        if (button) {
          button.disabled = false;
          button.textContent = previousLabel;
        }
      }
    }

    function summarizeResult(operation, state, elapsed, result) {
      if (state !== "done") {
        return `${operation}: ${state}`;
      }
      if (!result) {
        return `${operation} finished in ${elapsed}s.`;
      }
      if (operation === "simulate") {
        const metadata = result.metadata || {};
        const tps = metadata.tokens_per_second || {};
        return [
          "Reply:",
          result.reply || "",
          "",
          `elapsed: ${elapsed}s`,
          `model latency: ${metadata.latency_seconds ?? "unknown"}s`,
          `completion tok/s: ${tps.completion_tokens ?? "unknown"}`,
          `tokens: prompt ${metadata.prompt_tokens ?? "?"}, completion ${metadata.completion_tokens ?? "?"}, total ${metadata.total_tokens ?? "?"}`,
          "",
          "Raw model content is available from Logs / event metadata."
        ].join("\\n");
      }
      if (operation === "qq_send") {
        const verification = result.verification || {};
        if (!result.sent) {
          return [
            `QQ send blocked: ${result.reason}`,
            `elapsed: ${elapsed}s`,
            `expected group: ${verification.expected_group_name ?? "unknown"}`,
            `active group: ${verification.active_group_name ?? "unknown"}`,
            "",
            "Full send result is available from Logs / Status JSON."
          ].join("\\n");
        }
        return [
          "QQ send succeeded.",
          `elapsed: ${elapsed}s`,
          `duration: ${result.duration_seconds ?? "unknown"}s`,
          `active group: ${verification.active_group_name ?? "unknown"}`
        ].join("\\n");
      }
      if (operation === "qq_read") {
        return [
          "Visible QQ read completed.",
          `active group: ${result.active_group_name || "unknown"}`,
          `expected group: ${result.expected_group_name || "unset"}`,
          `target sender: ${result.target_sender_name || "unset"}`,
          `group matched: ${result.group_matched}`,
          `visible items: ${(result.visible_items || []).length}`,
          `target messages: ${(result.target_messages || []).length}`
        ].join("\\n");
      }
      if (operation.startsWith("loop_")) {
        const decisions = result.recent_decisions || result.handled || [];
        const last = decisions.length ? decisions[decisions.length - 1] : null;
        if (last) {
          return [
            `Loop ${operation.replace("loop_", "")} finished in ${elapsed}s.`,
            `running: ${result.running ?? "unknown"}`,
            `last action: ${last.action || "unknown"}`,
            `last reason: ${last.reason || "unknown"}`,
            `sent: ${last.sent ?? "unknown"}`,
            `send reason: ${last.send_reason || "unknown"}`,
            "",
            "Full loop state is available from Logs / Status JSON."
          ].join("\\n");
        }
        return [
          `Loop ${operation.replace("loop_", "")} finished in ${elapsed}s.`,
          `running: ${result.running ?? "unknown"}`,
          `reason: ${result.reason || "no new target messages"}`,
          "",
          "Full loop state is available from Logs / Status JSON."
        ].join("\\n");
      }
      if (operation === "model_runtime") {
        const process = result.process || {};
        const latest = result.latest_model_event || {};
        const metadata = latest.metadata || {};
        const tps = metadata.tokens_per_second || {};
        const configured = result.configured || {};
        return [
          "Model runtime ready.",
          `model: ${configured.model || "unknown"}`,
          `profile: ${(result.profiles || {}).active_profile || "unknown"}`,
          `pid: ${process.pid ?? "unknown"}`,
          `working set: ${process.working_set_mb ?? "unknown"} MB`,
          `latest completion tok/s: ${tps.completion_tokens ?? "unknown"}`,
          `latest latency: ${metadata.latency_seconds ?? "unknown"}s`
        ].join("\\n");
      }
      if (operation === "model_smoke") {
        const tps = result.tokens_per_second || {};
        return [
          "Model smoke completed.",
          result.content || "",
          "",
          `latency: ${result.latency_seconds ?? "unknown"}s`,
          `completion tok/s: ${tps.completion_tokens ?? "unknown"}`
        ].join("\\n");
      }
      if (operation === "offload_benchmark") {
        const lines = [
          "Offload benchmark completed.",
          `artifact: ${result.artifact_path || "unknown"}`,
          ""
        ];
        for (const item of result.results || []) {
          const summary = item.summary || {};
          lines.push(`${item.profile}: ${item.ok ? "ok" : "failed"}`);
          lines.push(`  gpu layers: ${(item.server || {}).n_gpu_layers ?? "?"}`);
          lines.push(`  avg completion tok/s: ${summary.avg_completion_tok_s ?? "unknown"}`);
          lines.push(`  avg prompt tok/s: ${summary.avg_prompt_tok_s ?? "unknown"}`);
          if (item.reason || item.error) {
            lines.push(`  reason: ${item.reason || item.error}`);
          }
        }
        return lines.join("\\n");
      }
      if (operation === "model_profiles") {
        return [
          "Model profiles loaded.",
          `active: ${result.active_profile || "unknown"}`,
          `profiles: ${Object.keys(result.profiles || {}).join(", ")}`
        ].join("\\n");
      }
      if (operation === "model_switch") {
        return [
          "Model switched.",
          `active: ${result.active_profile || "unknown"}`,
          `model: ${result.model || "unknown"}`,
          `download: ${(result.download || {}).reason || "unknown"}`,
          `model ready: ${((result.restart || {}).ready || {}).ok ?? false}`,
          `loop running: ${(result.loop_status || {}).running ?? "unknown"}`
        ].join("\\n");
      }
      if (operation === "model_stop_local") {
        return [
          "Local model stop requested.",
          `reason: ${(result.stop_result || {}).reason || "unknown"}`,
          `provider: ${(result.provider || {}).active_provider || "unknown"}`,
          `loop running: ${(result.loop_status || {}).running ?? "unknown"}`
        ].join("\\n");
      }
      if (operation === "raw_local_chat") {
        const usage = result.usage || {};
        const tps = result.tokens_per_second || {};
        return [
          "Raw local chat completed.",
          `model: ${result.model || "unknown"}`,
          `latency: ${result.latency_seconds ?? "unknown"}s`,
          `usage: ${formatUsageLine(usage)}`,
          `completion tok/s: ${tps.completion_tokens ?? "unknown"}`,
          "",
          result.content || ""
        ].join("\\n");
      }
      if (operation === "provider_status" || operation === "provider_switch" || operation === "provider_key") {
        const provider = result.provider || result;
        const budget = provider.budget || {};
        const grok = provider.grok || {};
        const routing = provider.routing || {};
        const rawLocal = provider.raw_local || {};
        const latestUsage = latestTraceUsage(provider.latest_trace || {});
        return [
          "Provider updated.",
          `active: ${provider.active_provider || "unknown"}`,
          `routing: gate=${routing.gate || "?"} final=${routing.final || "?"} utility=${routing.utility || "?"}`,
          `raw local: enabled=${rawLocal.enabled ?? false} max=${rawLocal.max_tokens ?? "?"} temp=${rawLocal.temperature ?? "?"} top_p=${rawLocal.top_p ?? "?"}`,
          `grok model: ${grok.model || "unknown"}`,
          `api key: ${grok.api_key_configured ? grok.api_key_masked || "configured" : "missing"}`,
          `usage telemetry: total=${formatInteger(budget.total_tokens)}, prompt=${formatInteger(budget.prompt_tokens)}, completion=${formatInteger(budget.completion_tokens)}`,
          `smoke budget reference: ${formatInteger(budget.budget)} (${formatPercentRatio(budget.used_ratio)} used)`,
          `runtime input cap: ${formatInteger(provider.runtime?.per_message_input_token_budget)} est. tokens/message`,
          `latest trace usage: ${latestUsage ? formatUsageLine(latestUsage) : "none"}`,
          `cloud loop allowed: ${(provider.safety || {}).cloud_loop_allowed ?? false}`,
          `QQ announcement: ${(result.announcement || {}).sent ?? false} ${(result.announcement || {}).reason || ""}`
        ].join("\\n");
      }
      if (operation === "provider_duplicate_soak") {
        return [
          `Duplicate soak ${result.ok ? "passed" : "failed"}.`,
          `queued block: ${(result.checks || {}).blocked_while_queued ?? "?"}`,
          `inflight block: ${(result.checks || {}).blocked_while_inflight ?? "?"}`,
          `completed block: ${(result.checks || {}).blocked_after_completed ?? "?"}`,
          `different message allowed: ${(result.checks || {}).different_can_enqueue ?? "?"}`
        ].join("\\n");
      }
      if (operation === "provider_test") {
        const tps = result.tokens_per_second || {};
        const usage = result.usage || {};
        return [
          "Provider test completed.",
          result.content || "",
          "",
          `latency: ${result.latency_seconds ?? "unknown"}s`,
          `usage: ${formatUsageLine(usage)}`,
          `completion tok/s: ${tps.completion_tokens ?? "unknown"}`,
          `trace: ${(result.metadata || {}).trace_id || "none"}`
        ].join("\\n");
      }
      if (operation === "provider_traces" || operation === "provider_latest_trace") {
        return `${operation} finished in ${elapsed}s. Trace data is available from Logs / Status JSON.`;
      }
      if (operation === "agent_settings" || operation === "agent_settings_update") {
        return [
          "Runtime settings loaded.",
          `default thinking: ${result.default_thinking_level ?? "unknown"}`,
          `activity: ${Number(result.activity ?? 0).toFixed(2)}`,
          `debug mode: ${result.debug_mode ?? 0}`
        ].join("\\n");
      }
      if (operation === "social_state" || operation === "social_state_update") {
        return [
          "Social state loaded.",
          `global mood: ${result.global_mood || "neutral"}`,
          `mood intensity: ${Number(result.mood_intensity ?? 0).toFixed(2)}`,
          `affinity: ${Number(result.affinity ?? 0.5).toFixed(2)}`,
          `source: ${result.source || "unknown"}`
        ].join("\\n");
      }
      if (operation === "memory_search") {
        return `Memory search finished in ${elapsed}s. Matches: ${(result || []).length}`;
      }
      if (operation === "web_read") {
        return [
          `Web read ${result.ok ? "succeeded" : "failed"}.`,
          `reason: ${result.reason || "unknown"}`,
          `title: ${result.title || "unknown"}`
        ].join("\\n");
      }
      if (operation === "agent_reboot") {
        return [
          "Agent reboot scheduled.",
          `reason: ${result.reason || "api"}`,
          "Watch runtime logs for the restart."
        ].join("\\n");
      }
      return `${operation} finished in ${elapsed}s. Details are available from Logs / Status JSON.`;
    }

    function updateSettingLabels() {
      const activity = Number(document.getElementById("activityLevel").value);
      document.getElementById("activityValue").textContent = activity.toFixed(2);
    }

    function syncSettingsForm(settings) {
      if (!settings) {
        return;
      }
      if (settings.default_thinking_level !== undefined) {
        document.getElementById("thinkLevel").value = String(settings.default_thinking_level);
      }
      if (settings.activity !== undefined) {
        document.getElementById("activityLevel").value = String(settings.activity);
      }
      if (settings.debug_mode !== undefined) {
        document.getElementById("debugMode").value = String(settings.debug_mode);
      }
      updateSettingLabels();
    }

    function syncModelProfiles(result) {
      const select = document.getElementById("modelProfile");
      if (!select || !result || !result.profiles) {
        return;
      }
      const active = result.active_profile || "";
      select.innerHTML = "";
      for (const [name, profile] of Object.entries(result.profiles)) {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = `${name} (${profile.model || "unknown"})${profile.exists ? "" : " - not downloaded"}`;
        option.selected = name === active;
        select.appendChild(option);
      }
    }

    function syncProviderStatus(provider) {
      if (!provider) {
        return;
      }
      const select = document.getElementById("providerSelect");
      if (select && provider.active_provider) {
        select.value = provider.active_provider;
      }
      const budget = provider.budget || {};
      const grok = provider.grok || {};
      const safety = provider.safety || {};
      const routing = provider.routing || {};
      const runtime = provider.runtime || {};
      const rawLocal = provider.raw_local || {};
      const latestTrace = provider.latest_trace || {};
      const apiUsageLines = formatApiUsage(provider).split("\\n");
      const lines = [
        `provider: ${provider.active_provider || "unloaded"}`,
        `routing: gate=${routing.gate || "?"} final=${routing.final || "?"} utility=${routing.utility || "?"}`,
        `raw local: enabled=${rawLocal.enabled ?? false} max=${rawLocal.max_tokens ?? "?"} temp=${rawLocal.temperature ?? "?"} top_p=${rawLocal.top_p ?? "?"}`,
        `raw local context: ${rawLocal.instructions || "unknown"} / ${rawLocal.context || "unknown"}`,
        `grok model: ${grok.model || "unknown"}`,
        `grok endpoint: ${grok.endpoint || "chat_completions"}`,
        `reasoning: simple=${grok.reasoning?.simple_chat || "?"} final=${grok.reasoning?.final_reply || "?"} web=${grok.reasoning?.web_fact || "?"}`,
        `cache: enabled=${grok.cache?.enabled ?? false} scope=${grok.cache?.scope || "default"}`,
        `api key: ${grok.api_key_configured ? grok.api_key_masked || "configured" : "missing"}`,
        `usage telemetry: total=${formatInteger(budget.total_tokens)}, input=${formatInteger(budget.prompt_tokens)}, output=${formatInteger(budget.completion_tokens)}, cached=${formatInteger(budget.cached_tokens)}, reasoning=${formatInteger(budget.reasoning_tokens)}`,
        `smoke budget reference: ${formatInteger(budget.budget)} (${formatPercentRatio(budget.used_ratio)} used)`,
        `runtime input cap: ${formatInteger(runtime.per_message_input_token_budget)} est. tokens/message, enforced=${runtime.enforce_input_budget ?? false}`,
        `daily usage gates runtime: ${!(runtime.daily_usage_is_telemetry_only ?? false)}`,
        `duplicate soak: ${safety.duplicate_soak_passed ?? false}`,
        `cloud loop allowed: ${safety.cloud_loop_allowed ?? false}`,
        `latest trace: ${latestTrace.trace_id || "none"}`
      ];
      const usageElement = document.getElementById("apiUsageSummary");
      if (usageElement) {
        usageElement.textContent = apiUsageLines.join("\\n");
      }
      const element = document.getElementById("providerSummary");
      if (element) {
        element.textContent = lines.join("\\n");
      }
    }

    function formatApiUsage(provider) {
      const budget = provider?.budget || {};
      const runtime = provider?.runtime || {};
      const grok = provider?.grok || {};
      const latestTrace = provider?.latest_trace || {};
      const latestUsage = latestTraceUsage(latestTrace);
      const lines = [
        `runtime input cap: ${formatInteger(runtime.per_message_input_token_budget)} estimated tokens/message`,
        `input cap enforced: ${runtime.enforce_input_budget ?? false}`,
        `daily usage gates runtime: ${!(runtime.daily_usage_is_telemetry_only ?? false)}`,
        `usage telemetry total: ${formatInteger(budget.total_tokens)} tokens`,
        `usage telemetry input: ${formatInteger(budget.prompt_tokens)}`,
        `usage telemetry output: ${formatInteger(budget.completion_tokens)}`,
        `usage telemetry cached: ${formatInteger(budget.cached_tokens)}`,
        `usage telemetry reasoning: ${formatInteger(budget.reasoning_tokens)}`,
        `usage telemetry sources/tools: ${formatInteger(budget.source_count)} / ${formatInteger(budget.tool_count)}`,
        `usage telemetry cost ticks: ${formatInteger(budget.cost_in_usd_ticks)} (${formatCostUsd(budget.cost_usd)})`,
        `smoke budget reference: ${formatInteger(budget.budget)} (${formatPercentRatio(budget.used_ratio)} used)`,
        `grok endpoint: ${grok.endpoint || "chat_completions"}`,
        `reasoning options: simple=${grok.reasoning?.simple_chat || "?"}, final=${grok.reasoning?.final_reply || "?"}, rewrite=${grok.reasoning?.rewrite || "?"}, web=${grok.reasoning?.web_fact || "?"}, complex=${grok.reasoning?.complex_reasoning || "?"}`,
        `cache: enabled=${grok.cache?.enabled ?? false}, scope=${grok.cache?.scope || "default"}`,
        `latest trace: ${latestTrace.trace_id || "none"}`,
      ];
      if (latestTrace.trace_id) {
        lines.push(`latest op: ${latestTrace.operation || "unknown"}, elapsed=${latestTrace.elapsed_seconds ?? "?"}s, error=${latestTrace.error || "none"}`);
      }
      if (latestUsage) {
        lines.push(`latest usage: ${formatUsageLine(latestUsage)}`);
        const promptDetails = latestUsage.prompt_tokens_details || latestUsage.input_tokens_details || {};
        const completionDetails = latestUsage.completion_tokens_details || latestUsage.output_tokens_details || {};
        if (Object.keys(promptDetails).length) {
          lines.push(`latest prompt details: text=${formatInteger(promptDetails.text_tokens)}, cached=${formatInteger(promptDetails.cached_tokens)}`);
        }
        if (Object.keys(completionDetails).length) {
          lines.push(`latest completion details: reasoning=${formatInteger(completionDetails.reasoning_tokens)}, accepted=${formatInteger(completionDetails.accepted_prediction_tokens)}, rejected=${formatInteger(completionDetails.rejected_prediction_tokens)}`);
        }
        if (latestUsage.num_sources_used !== undefined) {
          lines.push(`latest sources used: ${formatInteger(latestUsage.num_sources_used)}`);
        }
        if (latestUsage.cost_in_usd_ticks !== undefined) {
          lines.push(`latest cost ticks: ${formatInteger(latestUsage.cost_in_usd_ticks)} (${formatCostUsd(ticksToUsd(latestUsage.cost_in_usd_ticks))})`);
        }
      }
      return lines.join("\\n");
    }

    function formatApiUsagePill(provider) {
      const budget = provider?.budget || {};
      const runtime = provider?.runtime || {};
      const total = formatInteger(budget.total_tokens);
      const cap = formatInteger(runtime.per_message_input_token_budget);
      return `used=${total} input_cap=${cap}`;
    }

    function latestTraceUsage(trace) {
      const events = trace?.events || [];
      for (let index = events.length - 1; index >= 0; index -= 1) {
        const metadata = events[index]?.metadata || {};
        if (metadata.usage && typeof metadata.usage === "object") {
          return metadata.usage;
        }
      }
      return null;
    }

    function formatUsageLine(usage) {
      if (!usage || typeof usage !== "object") {
        return "none";
      }
      const prompt = formatInteger(usage.prompt_tokens ?? usage.input_tokens);
      const completion = formatInteger(usage.completion_tokens ?? usage.output_tokens);
      const total = formatInteger(usage.total_tokens);
      const promptDetails = usage.prompt_tokens_details || usage.input_tokens_details || {};
      const completionDetails = usage.completion_tokens_details || usage.output_tokens_details || {};
      const cached = promptDetails.cached_tokens;
      const reasoning = completionDetails.reasoning_tokens;
      const costTicks = usage.cost_in_usd_ticks;
      const cachedText = cached !== undefined ? `, cached=${formatInteger(cached)}` : "";
      const reasoningText = reasoning !== undefined ? `, reasoning=${formatInteger(reasoning)}` : "";
      const costText = costTicks !== undefined ? `, cost_ticks=${formatInteger(costTicks)}` : "";
      return `input=${prompt}, output=${completion}, total=${total}${cachedText}${reasoningText}${costText}`;
    }

    function formatCostUsd(value) {
      const number = Number(value || 0);
      if (!Number.isFinite(number) || number <= 0) {
        return "$0";
      }
      return `$${number.toFixed(6)}`;
    }

    function ticksToUsd(value) {
      const number = Number(value || 0);
      if (!Number.isFinite(number)) {
        return 0;
      }
      return number / 100000000;
    }

    function formatPercentRatio(value) {
      const number = Number(value || 0);
      if (!Number.isFinite(number)) {
        return "?";
      }
      return `${Math.round(number * 10000) / 100}%`;
    }

    function formatRatio(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return "?";
      }
      return number.toFixed(2);
    }

    function formatInteger(value) {
      if (value === undefined || value === null || value === "") {
        return "0";
      }
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return String(value);
      }
      return Math.round(number).toLocaleString();
    }

    function updateSocialLabels() {
      const mood = Number(document.getElementById("moodIntensity").value);
      const affinity = Number(document.getElementById("affinityLevel").value);
      const globalAffinity = Number(document.getElementById("globalAffinity").value);
      document.getElementById("moodIntensityValue").textContent = mood.toFixed(2);
      document.getElementById("affinityValue").textContent = affinity.toFixed(2);
      document.getElementById("globalAffinityValue").textContent = globalAffinity.toFixed(2);
    }

    function updateMemoryLabels() {
      const confidence = Number(document.getElementById("memoryConfidence").value);
      document.getElementById("memoryConfidenceValue").textContent = confidence.toFixed(2);
    }

    function syncSocialForm(state) {
      if (!state) {
        return;
      }
      if (state.global_mood !== undefined) {
        document.getElementById("globalMood").value = state.global_mood || "";
      }
      if (state.mood_intensity !== undefined) {
        document.getElementById("moodIntensity").value = String(state.mood_intensity);
      }
      if (state.affinity !== undefined) {
        document.getElementById("affinityLevel").value = String(state.affinity);
      }
      if (state.global_affinity !== undefined) {
        document.getElementById("globalAffinity").value = String(state.global_affinity);
      }
      updateSocialLabels();
    }

    function syncGlobalSocialForm(state) {
      if (!state) {
        return;
      }
      if (state.global_mood !== undefined) {
        document.getElementById("globalMood").value = state.global_mood || "";
      }
      if (state.mood_intensity !== undefined) {
        document.getElementById("moodIntensity").value = String(state.mood_intensity);
      }
      if (state.global_affinity !== undefined) {
        document.getElementById("globalAffinity").value = String(state.global_affinity);
      }
      updateSocialLabels();
    }

    function syncSocialProfile(profilePayload) {
      const profile = profilePayload?.profile || profilePayload || {};
      const snapshot = profilePayload?.snapshot || {};
      if (profile.user_name) {
        document.getElementById("socialUserName").value = profile.user_name;
      }
      if (profile.affinity !== undefined) {
        document.getElementById("affinityLevel").value = String(profile.affinity);
      } else if (snapshot.affinity !== undefined) {
        document.getElementById("affinityLevel").value = String(snapshot.affinity);
      }
      document.getElementById("userLanguagePreference").value = profile.language_preference || "";
      document.getElementById("userTonePreference").value = profile.tone_preference || "";
      document.getElementById("userAliases").value = (profile.aliases || []).join(", ");
      document.getElementById("userRelationshipNotes").value = profile.relationship_notes || "";
      document.getElementById("socialProfileDetails").textContent = JSON.stringify({
        user_name: profile.user_name || socialStateUserName(),
        first_seen: profile.first_seen || "",
        last_seen: profile.last_seen || "",
        message_count: profile.message_count ?? 0,
        interaction_count: profile.interaction_count ?? 0,
        affinity: profile.affinity ?? snapshot.affinity,
        affinity_source: profile.affinity_source || snapshot.source || "",
        last_affinity_change_reason: profile.last_affinity_change_reason || "",
        recent_positive: profile.recent_positive || [],
        recent_negative: profile.recent_negative || []
      }, null, 2);
      syncSocialForm(snapshot);
    }

    function renderSocialUsers(payload) {
      const users = payload?.users || [];
      const select = document.getElementById("socialUserList");
      const current = socialStateUserName();
      select.innerHTML = "";
      for (const user of users) {
        const option = document.createElement("option");
        option.value = user.user_name;
        option.textContent = `${user.user_name}  affinity=${formatRatio(user.affinity)}  messages=${user.message_count || 0}`;
        if (user.user_name === current) {
          option.selected = true;
        }
        select.appendChild(option);
      }
      if (!select.value && users.length) {
        select.value = users[0].user_name;
        document.getElementById("socialUserName").value = users[0].user_name;
      }
    }

    function renderTopStatus(status, loopStatus) {
      if (status) {
        cachedStatus = {...(cachedStatus || {}), ...status};
      }
      if (loopStatus) {
        cachedLoopStatus = loopStatus;
      }

      const baseStatus = cachedStatus || {};
      const loop = cachedLoopStatus || baseStatus.agent_loop || {};
      const qq = baseStatus.onebot || {};
      const modelProfile = baseStatus.model_profile || {};
      const provider = baseStatus.provider || {};
      const activity = loop.activity || {};
      const metadata = activity.metadata || {};
      const recent = loop.recent_decisions || [];
      const latest = recent.length ? recent[recent.length - 1] : null;

      const modelText = `${modelProfile.active_profile || "unknown"} / ${modelProfile.model || "unknown"}`;
      const providerText = `${provider.active_provider || "unloaded"} ${provider.grok?.model || ""}`.trim();
      const apiUsageText = formatApiUsagePill(provider);
      const qqText = `connected=${qq.connected ?? false} ready=${qq.ready ?? false} group=${qq.target_group_id || "unset"}`;
      const loopText = `running=${loop.running ?? "?"} ${activity.stage || ""}`.trim();
      const pendingCount = loop.pending_message_count ?? 0;
      const queuedCount = loop.queued_message_count ?? 0;
      const inflightCount = loop.inflight_message_count ?? 0;
      const aggregatingCount = loop.aggregating_message_count ?? 0;
      const busyText = loop.active_message ? "model" : (loop.tick_busy ? "read" : "idle");
      const queueText = `agg=${aggregatingCount} pending=${pendingCount} queued=${queuedCount} inflight=${inflightCount} busy=${busyText}`;
      const activeText = activity.message_text || activity.detail || "none";
      const latestText = latest ? `${latest.action || "?"} ${latest.reason || ""}`.trim() : (metadata.action || "none");

      setText("topModel", modelText);
      setText("topProvider", providerText);
      setText("topApiUsage", apiUsageText);
      setText("topQQ", qqText);
      setText("topLoop", loopText);
      setText("topQueue", queueText);
      setText("topActive", activeText);
      setText("topLatest", latestText);
      setText("metricModel", modelText);
      setText("metricQQ", qqText);
      setText("metricApiUsage", apiUsageText);
      setText("metricLoop", loopText);
      setText("metricDecision", latestText);
      syncProviderStatus(provider);
      if (baseStatus.remote_debug) {
        renderRemoteDebugStatus(baseStatus.remote_debug);
      }
      if (baseStatus.debug_chat) {
        renderDebugChatStatus(baseStatus.debug_chat);
      }
    }

    function setText(id, value) {
      const element = document.getElementById(id);
      if (element) {
        element.textContent = value;
      }
    }

    async function refreshTopStatus() {
      try {
        const status = await requestJson("/api/debug/compact-status");
        renderTopStatus(status, status.agent_loop);
      } catch (_) {
        // The main output panel already reports action-level failures.
      }
    }

    function renderLoopActivity(result) {
      latestLoopStatus = result || null;
      const activity = (result && result.activity) || {};
      const metadata = activity.metadata || {};
      const active = result?.active_message || null;
      const recent = result?.recent_decisions || [];
      const latestDecision = recent.length ? recent[recent.length - 1] : null;
      const lines = [
        `running: ${result?.running ?? "unknown"}`,
        `stage: ${activity.stage || "unknown"}`,
        `detail: ${activity.detail || ""}`,
        `sender: ${activity.sender_name || ""}`,
        `message: ${activity.message_text || ""}`,
        `aggregating: ${result?.aggregating_message_count ?? 0}, pending: ${result?.pending_message_count ?? 0}, queued: ${result?.queued_message_count ?? 0}, inflight: ${result?.inflight_message_count ?? 0}`,
      ];
      if (active) {
        lines.push(`busy message: ${active.message_text || ""}`);
        lines.push(`busy identity: ${active.clean_identity || ""}`);
      }
      if (metadata.action || metadata.reason || metadata.used_model !== undefined) {
        lines.push(`decision: ${metadata.action || ""} ${metadata.reason || ""}`.trim());
        lines.push(`used model: ${metadata.used_model ?? ""}`);
      }
      if (metadata.gate_decision) {
        const gate = metadata.gate_decision;
        lines.push(`gate: ${gate.action || "unknown"} ${gate.reason || ""}`.trim());
        lines.push(`attention: ${gate.attention || "unknown"} score ${gate.attention_score ?? "?"}`);
        lines.push(`expected latency: ${gate.expected_latency_class || "unknown"} ${gate.predicted_latency_seconds ?? "?"}s`);
      }
      if (metadata.engagement_decision) {
        lines.push(formatEngagementLine(metadata.engagement_decision));
      }
      if (metadata.placeholder_sent !== undefined || metadata.placeholder_text) {
        lines.push(`placeholder: ${metadata.placeholder_sent ?? false} ${metadata.placeholder_text || ""}`.trim());
      }
      if (metadata.thinking_level !== undefined || metadata.web_used !== undefined) {
        lines.push(`thinking: effective ${metadata.thinking_level ?? "unknown"}, max ${metadata.max_thinking_level ?? "?"}, requested ${metadata.requested_thinking_level ?? "none"}`);
        if (metadata.thinking_directive) {
          lines.push(`thinking directive: ${metadata.thinking_directive}`);
        }
        lines.push(`web: ${metadata.web_used ?? false} ${metadata.web_query || ""}`.trim());
      }
      if (metadata.latency_seconds || metadata.prompt_tokens || metadata.completion_tokens) {
        lines.push(`model: ${metadata.latency_seconds ?? "?"}s, prompt ${metadata.prompt_tokens ?? "?"}, completion ${metadata.completion_tokens ?? "?"}`);
      }
      if (metadata.token_usage) {
        lines.push(formatTokenUsageLine(metadata.token_usage));
      }
      if (metadata.interaction_plan) {
        lines.push(formatInteractionLine(metadata.interaction_plan));
      }
      if (metadata.quality_review) {
        lines.push(formatQualityLine(metadata));
      }
      if (latestDecision) {
        lines.push(`latest decision: ${latestDecision.action || ""} ${latestDecision.reason || ""}`.trim());
        lines.push(`latest sent: ${latestDecision.sent ?? false} ${latestDecision.send_reason || ""}`.trim());
      }
      if (metadata.stage_timings) {
        lines.push(`elapsed: ${metadata.stage_timings.total_seconds ?? "?"}s`);
      }
      document.getElementById("loopActivity").textContent = lines.join("\\n");
      renderQueueInspector(result);
      renderLlmTrace(result);
      renderTopStatus(null, result);
    }

    function renderQueueInspector(result) {
      const active = result?.active_message || null;
      const aggregating = result?.aggregating_messages || [];
      const pending = result?.pending_messages || [];
      const ledger = result?.ledger || {};
      const ledgerCounts = ledger.counts || {};
      const lines = [
        `aggregating_count: ${result?.aggregating_message_count ?? 0}`,
        `pending_count: ${result?.pending_message_count ?? 0}`,
        `queued_count: ${result?.queued_message_count ?? 0}`,
        `inflight_count: ${result?.inflight_message_count ?? 0}`,
        `ledger: observed=${ledgerCounts.observed ?? 0} queued=${ledgerCounts.queued ?? 0} inflight=${ledgerCounts.inflight ?? 0} completed=${ledgerCounts.completed ?? 0} suppressed=${ledgerCounts.suppressed ?? 0}`
      ];
      const items = [];
      if (active) {
        items.push(messageButton("active", -1, active));
      }
      aggregating.forEach((message, index) => {
        items.push(messageButton("aggregating", index, message));
      });
      pending.forEach((message, index) => {
        items.push(messageButton("pending", index, message));
      });
      const html = [
        `<div class="mono-small">${escapeHtml(lines.join("\\n"))}</div>`,
        items.length ? `<div class="message-list">${items.join("")}</div>` : "<p>No pending or active messages.</p>"
      ].join("");
      document.getElementById("queueInspector").innerHTML = html;
    }

    function messageButton(kind, index, message) {
      const title = `${kind}: ${message.sender_name || ""}`;
      const text = message.message_text || message.clean_text || "";
      const identity = message.clean_identity || message.fingerprint || "";
      return [
        `<button class="message-item" onclick="inspectLoopMessage('${kind}', ${index})">`,
        `<strong>${escapeHtml(title)}</strong>`,
        `<span>${escapeHtml(text)}</span>`,
        `<span class="mono-small">${escapeHtml(identity)}</span>`,
        "</button>"
      ].join("");
    }

    function renderLlmTrace(result) {
      const activity = result?.activity || {};
      const metadata = activity.metadata || {};
      const recent = result?.recent_decisions || [];
      const latest = recent.length ? recent[recent.length - 1] : null;
      const latestMetadata = latest?.metadata || {};
      const active = result?.active_message || null;
      const modelMetadata = metadata.latency_seconds || metadata.prompt_tokens ? metadata : latestMetadata;
      const tps = modelMetadata.tokens_per_second || {};
      const lines = [
        `stage: ${activity.stage || "unknown"}`,
        `detail: ${activity.detail || ""}`,
        `active: ${active ? active.message_text || "" : "none"}`,
        `previous decision: ${latest ? `${latest.action || ""} ${latest.reason || ""}`.trim() : "none"}`,
        `sent: ${latest ? `${latest.sent ?? false} ${latest.send_reason || ""}`.trim() : "none"}`,
        `reply: ${modelMetadata.cleaned_reply || modelMetadata.agent_reply || ""}`,
        `raw model: ${modelMetadata.raw_model_content || ""}`,
        `tokens: prompt=${modelMetadata.prompt_tokens ?? "?"} completion=${modelMetadata.completion_tokens ?? "?"} total=${modelMetadata.total_tokens ?? "?"}`,
        formatTokenUsageLine(modelMetadata.token_usage),
        `tok/s: prompt=${tps.prompt_tokens ?? "?"} completion=${tps.completion_tokens ?? "?"} total=${tps.total_tokens ?? "?"}`,
        `latency: ${modelMetadata.latency_seconds ?? "?"}s`,
        `thinking: requested=${modelMetadata.requested_thinking_level ?? "auto"} effective=${modelMetadata.thinking_level ?? "?"}`,
        modelMetadata.engagement_decision ? formatEngagementLine(modelMetadata.engagement_decision) : "engagement: none",
        `interaction: ${modelMetadata.interaction_plan ? `${modelMetadata.interaction_plan.mode || "unknown"} hook=${modelMetadata.interaction_plan.hook_budget ?? "?"} affinity=${modelMetadata.interaction_plan.affinity ?? "?"}` : "none"}`,
        `quality: ${modelMetadata.quality_review ? `score=${modelMetadata.quality_review.score ?? "?"} rewrite=${modelMetadata.quality_rewrite_used ?? false}` : "none"}`,
        `provider: decision=${modelMetadata.provider_decision ?? false} trace=${modelMetadata.provider_trace_id || "none"}`,
        `web: used=${modelMetadata.web_used ?? false} search=${modelMetadata.search_used ?? false} query=${modelMetadata.web_query || ""}`,
        `sources: ${(modelMetadata.web_sources || []).length || 0}`
      ];
      const text = lines.join("\\n");
      document.getElementById("llmTrace").textContent = text;
      const consoleElement = document.getElementById("consoleLlmNow");
      if (consoleElement) {
        consoleElement.textContent = text;
      }
    }

    function formatEngagementLine(decision) {
      if (!decision || typeof decision !== "object") {
        return "engagement: none";
      }
      return `engagement: ${decision.action || "?"} p=${decision.reply_probability ?? "?"} roll=${decision.roll ?? "direct"} direct=${decision.directness || "?"} hook=${decision.continuation_budget ?? "?"}`;
    }

    function formatTokenUsageLine(tokenUsage) {
      if (!tokenUsage || typeof tokenUsage !== "object") {
        return "tokens: local=? api=?";
      }
      const local = (tokenUsage.local || {}).total || {};
      const api = (tokenUsage.api || {}).total || {};
      return [
        `tokens: local=${local.prompt ?? "?"}/${local.completion ?? "?"}/${local.total ?? "?"}`,
        `api=${api.input ?? "?"}/${api.output ?? "?"}/${api.total ?? "?"}`,
        `cached=${api.cached ?? "?"}`,
        `reasoning=${api.reasoning ?? "?"}`,
        `local_latency=${local.latency_seconds ?? "?"}s`,
        `api_latency=${api.latency_seconds ?? "?"}s`
      ].join(" ");
    }

    function inspectLoopMessage(kind, index) {
      if (!latestLoopStatus) {
        return;
      }
      let message = null;
      if (kind === "active") {
        message = latestLoopStatus.active_message;
      } else if (kind === "aggregating") {
        message = (latestLoopStatus.aggregating_messages || [])[index] || null;
      } else {
        message = (latestLoopStatus.pending_messages || [])[index] || null;
      }
      if (!message) {
        showText("summary", "Message is no longer in the loop queue.");
        return;
      }
      showText("summary", [
        `${kind} message`,
        `sender: ${message.sender_name || ""}`,
        `clean: ${message.message_text || ""}`,
        `raw: ${message.raw_message_text || ""}`,
        `identity: ${message.clean_identity || ""}`,
        `fingerprint: ${message.fingerprint || ""}`
      ].join("\\n"));
      showOutput({state: "snapshot", operation: "message_inspect", result: message});
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function loopSnapshot(result) {
      const activity = result.activity || {};
      const metadata = activity.metadata || {};
      const recent = result.recent_decisions || [];
      const latest = recent.length ? recent[recent.length - 1] : null;
      return {
        running: result.running,
        stage: activity.stage,
        detail: activity.detail,
        message_text: activity.message_text,
        pending_message_count: result.pending_message_count,
        queued_message_count: result.queued_message_count,
        inflight_message_count: result.inflight_message_count,
        active_message: result.active_message,
        decision: metadata.action ? {
          action: metadata.action,
          reason: metadata.reason,
          used_model: metadata.used_model,
          latency_seconds: metadata.latency_seconds,
          prompt_tokens: metadata.prompt_tokens,
          completion_tokens: metadata.completion_tokens,
          tokens_per_second: metadata.tokens_per_second,
          thinking_level: metadata.thinking_level,
          web_used: metadata.web_used,
          web_query: metadata.web_query
        } : null,
        latest_decision: latest ? compactDecision(latest) : null
      };
    }

    async function refreshLoopActivity() {
      try {
        const result = await requestJson("/api/agent-loop/status");
        renderLoopActivity(result);
        const activity = result.activity || {};
        const metadata = activity.metadata || {};
        const key = [
          activity.stage || "",
          activity.message_text || "",
          metadata.action || "",
          metadata.reason || "",
          result.pending_message_count ?? 0,
          result.inflight_message_count ?? 0,
          result.active_message?.clean_identity || ""
        ].join("|");
        if (key && key !== lastLoopActivityKey) {
          lastLoopActivityKey = key;
          refreshDebugTimeline();
        }
      } catch (error) {
        document.getElementById("loopActivity").textContent = `loop status failed: ${String(error.message || error)}`;
      }
    }

    async function refreshDebugTimeline() {
      try {
        const result = await requestJson("/api/debug/timeline?limit=80");
        renderChatTimeline(result.items || []);
        showOutput({
          state: "snapshot",
          operation: "debug_timeline",
          result
        }, "debug_timeline");
      } catch (_) {
        // Keep the existing output if the backend is restarting.
      }
    }

    async function loadStatus() {
      await runTimed("status", "refreshButton", async () => {
        const result = await requestJson("/api/status");
        show("status", result);
        renderTopStatus(result, result.agent_loop);
        syncSettingsForm(result.agent_settings);
        if (result.model_profile && result.model_profile.active_profile) {
          const loaded = await requestJson("/api/model/profiles");
          syncModelProfiles(loaded);
        }
        return result;
      });
    }

    async function loadModelProfiles() {
      await runTimed("model_profiles", "modelProfilesButton", async () => {
        const result = await requestJson("/api/model/profiles");
        syncModelProfiles(result);
        return result;
      });
    }

    async function switchModel() {
      const profile = document.getElementById("modelProfile").value;
      await runTimed("model_switch", "modelSwitchButton", async () => {
        const result = await requestJson("/api/model/switch", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({profile, restart_loop: true})
        });
        await loadModelProfiles();
        await loadStatus();
        return result;
      });
    }

    async function stopLocalModel() {
      await runTimed("model_stop_local", "modelStopLocalButton", async () => requestJson("/api/model/stop-local", {
        method: "POST"
      }));
      await refreshTopStatus();
    }

    async function loadProviderStatus() {
      await runTimed("provider_status", "providerStatusButton", async () => {
        const result = await requestJson("/api/provider/status");
        syncProviderStatus(result);
        return result;
      });
    }

    async function switchProvider() {
      const provider = document.getElementById("providerSelect").value;
      await runTimed("provider_switch", "providerSwitchButton", async () => {
        const result = await requestJson("/api/provider/switch", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({provider, restart_loop: true, announce_to_qq: true})
        });
        syncProviderStatus(result.provider);
        return result;
      });
    }

    async function switchProviderTo(provider) {
      const select = document.getElementById("providerSelect");
      if (select) {
        select.value = provider;
      }
      await switchProvider();
    }

    async function saveProviderKey() {
      const apiKey = document.getElementById("xaiApiKey").value.trim();
      await runTimed("provider_key", "providerKeyButton", async () => {
        const result = await requestJson("/api/provider/api-key", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({api_key: apiKey})
        });
        document.getElementById("xaiApiKey").value = "";
        syncProviderStatus(result);
        return result;
      });
    }

    async function testProvider() {
      const message = document.getElementById("providerTestMessage").value;
      await runTimed("provider_test", "providerTestButton", async () => requestJson("/api/provider/test", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message})
      }));
    }

    async function runProviderSoak() {
      await runTimed("provider_duplicate_soak", "providerSoakButton", async () => requestJson("/api/provider/duplicate-soak", {
        method: "POST"
      }));
      await loadProviderStatus();
    }

    async function loadProviderTraces() {
      await runTimed("provider_traces", "providerStatusButton", async () => requestJson("/api/provider/traces?limit=20"));
    }

    async function loadLatestProviderTrace() {
      await runTimed("provider_latest_trace", "providerStatusButton", async () => {
        const traces = await requestJson("/api/provider/traces?limit=1");
        if (!traces.length) {
          return {trace: null};
        }
        return requestJson(`/api/provider/traces/${encodeURIComponent(traces[0].trace_id)}`);
      });
    }

    async function modelSmoke() {
      const message = document.getElementById("modelSmokeMessage").value;
      await runTimed("model_smoke", "modelSmokeButton", async () => requestJson("/api/model/smoke", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message})
      }));
    }

    async function rawLocalChat() {
      const stop = document.getElementById("rawLocalStop").value
        .split(/\\r?\\n/)
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      const body = {
        message: document.getElementById("rawLocalMessage").value,
        max_tokens: Number(document.getElementById("rawLocalMaxTokens").value),
        temperature: Number(document.getElementById("rawLocalTemperature").value),
        top_p: Number(document.getElementById("rawLocalTopP").value),
        stop
      };
      await runTimed("raw_local_chat", "rawLocalChatButton", async () => requestJson("/api/model/raw-chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
    }

    async function runOffloadBenchmark() {
      const profiles = document.getElementById("offloadProfiles").value
        .split(/\\r?\\n/)
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      await runTimed("offload_benchmark", "offloadBenchmarkButton", async () => requestJson("/api/model/benchmark-offload", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({profiles, restore_loop: true})
      }));
      await loadModelRuntime();
    }

    async function loadAgentSettings() {
      await runTimed("agent_settings", "settingsLoadButton", async () => {
        const result = await requestJson("/api/agent/settings");
        syncSettingsForm(result);
        return result;
      });
    }

    async function applyAgentSettings() {
      const body = {
        default_thinking_level: Number(document.getElementById("thinkLevel").value),
        activity: Number(document.getElementById("activityLevel").value),
        debug_mode: Number(document.getElementById("debugMode").value)
      };
      await runTimed("agent_settings_update", "settingsApplyButton", async () => {
        const result = await requestJson("/api/agent/settings", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        syncSettingsForm(result);
        return result;
      });
    }

    function socialStateUserName() {
      return document.getElementById("socialUserName").value.trim() || "group member";
    }

    async function loadSocialUsers() {
      await runTimed("social_users", "socialUsersButton", async () => {
        const result = await requestJson("/api/social-state/users");
        renderSocialUsers(result);
        if (document.getElementById("socialUserList").value) {
          await loadSocialProfile();
        }
        return result;
      });
    }

    function selectSocialUser(userName) {
      if (!userName) {
        return;
      }
      document.getElementById("socialUserName").value = userName;
      loadSocialProfile();
    }

    async function loadSocialProfile() {
      await runTimed("social_profile", "socialLoadButton", async () => {
        const result = await requestJson(`/api/social-state/profile?user_name=${encodeURIComponent(socialStateUserName())}`);
        syncSocialProfile(result);
        return result;
      });
    }

    async function loadSocialState() {
      return loadSocialProfile();
    }

    async function applySocialState() {
      const body = {
        user_name: socialStateUserName(),
        affinity: Number(document.getElementById("affinityLevel").value),
        aliases: document.getElementById("userAliases").value.split(",").map((item) => item.trim()).filter(Boolean),
        language_preference: document.getElementById("userLanguagePreference").value,
        tone_preference: document.getElementById("userTonePreference").value,
        relationship_notes: document.getElementById("userRelationshipNotes").value,
        note: document.getElementById("socialNote").value
      };
      await runTimed("social_state_update", "socialApplyButton", async () => {
        const result = await requestJson("/api/social-state/profile/override", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        syncSocialProfile(result);
        await loadSocialUsers();
        return result;
      });
    }

    async function loadGlobalSocialState() {
      await runTimed("social_global", "socialGlobalLoadButton", async () => {
        const result = await requestJson("/api/social-state/global");
        syncGlobalSocialForm(result);
        return result;
      });
    }

    async function applyGlobalSocialState() {
      const body = {
        global_mood: document.getElementById("globalMood").value,
        mood_intensity: Number(document.getElementById("moodIntensity").value),
        global_affinity: Number(document.getElementById("globalAffinity").value),
        note: document.getElementById("globalSocialNote").value
      };
      await runTimed("social_global_update", "socialGlobalApplyButton", async () => {
        const result = await requestJson("/api/social-state/global", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        syncGlobalSocialForm(result);
        return result;
      });
    }

    async function loadSocialChanges() {
      await runTimed("social_changes", "socialChangesButton", async () => requestJson("/api/social-state/changes?limit=30"));
    }

    async function loadQQStatus() {
      await runTimed("onebot_status", "qqStatusButton", async () => {
        const result = await requestJson("/api/onebot/status");
        show("status", {onebot: result});
        renderTopStatus({onebot: result}, null);
        return result;
      });
    }

    async function loadModelRuntime() {
      await runTimed("model_runtime", "runtimeButton", async () => {
        const result = await requestJson("/api/model/runtime");
        show("status", result);
        return result;
      });
    }

    async function loadEvents() {
      await runTimed("events", "eventsButton", async () => requestJson("/api/events/recent?limit=20"));
    }

    async function loadTimeline() {
      await runTimed("debug_timeline", "timelineButton", async () => requestJson("/api/debug/timeline?limit=100"));
    }

    async function loadMemory() {
      await runTimed("memory", "memoryButton", async () => requestJson("/api/memory/recent?limit=30"));
    }

    async function searchMemory() {
      const query = document.getElementById("memorySearchQuery").value.trim();
      await runTimed("memory_search", "memorySearchButton", async () => requestJson("/api/memory/search", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query: query || " ", limit: 20})
      }));
    }

    function parseMetadataJson() {
      const raw = document.getElementById("memoryMetadata").value.trim() || "{}";
      try {
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("metadata must be a JSON object");
        }
        return parsed;
      } catch (error) {
        throw new Error(`Invalid metadata JSON: ${String(error.message || error)}`);
      }
    }

    async function saveMemory() {
      const idText = document.getElementById("memoryId").value.trim();
      const body = {
        id: idText ? Number(idText) : null,
        kind: document.getElementById("memoryKind").value,
        summary: document.getElementById("memorySummary").value,
        confidence: Number(document.getElementById("memoryConfidence").value),
        metadata: parseMetadataJson()
      };
      await runTimed("memory_save", "memorySaveButton", async () => requestJson("/api/memory/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
      await loadMemory();
    }

    async function deleteMemory() {
      const idText = document.getElementById("memoryId").value.trim();
      const query = document.getElementById("memoryDeleteQuery").value.trim();
      const body = {
        id: idText ? Number(idText) : null,
        query: idText ? "" : query,
        limit: 50
      };
      await runTimed("memory_delete", "memoryDeleteButton", async () => requestJson("/api/memory/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
      await loadMemory();
    }

    async function saveShortTerm() {
      const body = {
        source: "debug_ui",
        kind: "manual_context",
        content: document.getElementById("shortTermContent").value,
        metadata: {manual: true}
      };
      await runTimed("short_term_save", "shortTermSaveButton", async () => requestJson("/api/events/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
      await loadEvents();
    }

    async function simulateChat() {
      const body = {
        user_name: document.getElementById("userName").value,
        message: document.getElementById("message").value
      };
      await runTimed("simulate", "simulateButton", async () => requestJson("/api/chat/simulate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
    }

    async function debugChatStatus() {
      const result = await runTimed("debug_chat_status", "debugChatStatusButton", async () => requestJson("/api/debug-chat/status"));
      if (result) {
        renderDebugChatStatus(result);
      }
    }

    async function debugChatStart() {
      const result = await runTimed("debug_chat_start", "debugChatStartButton", async () => requestJson("/api/debug-chat/start", {method: "POST"}));
      if (result) {
        renderDebugChatStatus(result);
      }
    }

    async function debugChatStop() {
      const result = await runTimed("debug_chat_stop", "debugChatStopButton", async () => requestJson("/api/debug-chat/stop", {method: "POST"}));
      if (result) {
        renderDebugChatStatus(result);
      }
    }

    async function debugChatSend() {
      const maxTokens = Number(document.getElementById("debugChatMaxTokens").value);
      const body = {
        user_name: document.getElementById("debugChatUser").value,
        message: document.getElementById("debugChatMessage").value,
        max_tokens: Number.isFinite(maxTokens) ? maxTokens : 700
      };
      const result = await runTimed("debug_chat_message", "debugChatSendButton", async () => requestJson("/api/debug-chat/message", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      }));
      if (result) {
        document.getElementById("debugChatMessage").value = "";
        renderDebugChatStatus(result);
      }
    }

    async function remoteDebugStatus() {
      const result = await runTimed("remote_debug_status", "remoteDebugStatusButton", async () => requestJson("/api/remote-debug/status"));
      if (result) {
        renderRemoteDebugStatus(result);
      }
    }

    async function remoteDebugStart() {
      const result = await runTimed("remote_debug_start", "remoteDebugStartButton", async () => requestJson("/api/remote-debug/start", {method: "POST"}));
      if (result) {
        renderRemoteDebugStatus(result);
      }
    }

    async function remoteDebugStop() {
      const result = await runTimed("remote_debug_stop", "remoteDebugStopButton", async () => requestJson("/api/remote-debug/stop", {method: "POST"}));
      if (result) {
        renderRemoteDebugStatus(result);
      }
    }

    async function loadOneBotGroups() {
      await runTimed("onebot_groups", "onebotGroupsButton", async () => requestJson("/api/onebot/groups"));
    }

    async function loadOneBotEvents() {
      await runTimed("onebot_events", "onebotEventsButton", async () => requestJson("/api/onebot/events/recent?limit=50"));
    }

    async function selectOneBotGroup() {
      const groupId = document.getElementById("onebotGroupId").value.trim();
      await runTimed("onebot_group_select", "onebotSelectGroupButton", async () => requestJson("/api/onebot/group/select", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({group_id: groupId})
      }));
      await refreshTopStatus();
    }

    async function qqSend() {
      await runTimed("onebot_send", "qqSendButton", async () => requestJson("/api/onebot/send-test", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: document.getElementById("qqText").value})
      }));
      await refreshTopStatus();
    }

    async function loopStart() {
      const result = await runTimed("loop_start", "loopStartButton", async () => requestJson("/api/agent-loop/start", {method: "POST"}));
      if (result) renderLoopActivity(result);
    }

    async function loopStop() {
      const result = await runTimed("loop_stop", "loopStopButton", async () => requestJson("/api/agent-loop/stop", {method: "POST"}));
      if (result) renderLoopActivity(result);
    }

    async function loopTick() {
      const result = await runTimed("loop_tick", "loopTickButton", async () => requestJson("/api/agent-loop/tick", {method: "POST"}));
      if (result) await refreshLoopActivity();
    }

    async function loopCollectScrollback() {
      const result = await runTimed("loop_scrollback", "loopScrollbackButton", async () => requestJson("/api/agent-loop/collect-scrollback?pages=3", {method: "POST"}));
      if (result) await refreshLoopActivity();
    }

    async function loopStatus() {
      const result = await runTimed("loop_status", "loopStatusButton", async () => requestJson("/api/agent-loop/status"));
      if (result) renderLoopActivity(result);
    }

    async function triggerSpontaneous() {
      await runTimed("spontaneous", "spontaneousButton", async () => requestJson("/api/agent/spontaneous", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({context: document.getElementById("spontaneousContext").value})
      }));
    }

    async function triggerSpontaneousFromSettings() {
      await runTimed("spontaneous", "settingsSpontaneousButton", async () => requestJson("/api/agent/spontaneous", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({context: "Manual trigger from runtime settings panel."})
      }));
    }

    async function manualForceReply() {
      const eventText = document.getElementById("manualReplyEvent").value.trim();
      const eventId = eventText ? Number(eventText) : null;
      const payload = {
        sender_name: document.getElementById("manualReplySender").value.trim(),
        message_text: document.getElementById("manualReplyMessage").value.trim(),
        event_id: Number.isFinite(eventId) ? eventId : null,
        extra_instruction: document.getElementById("manualReplyInstruction").value,
        send_to_qq: document.getElementById("manualReplySendToQQ").checked
      };
      await runTimed("manual_force_reply", "manualForceReplyButton", async () => requestJson("/api/agent-loop/manual-reply", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }));
      await refreshDebugTimeline();
    }

    async function webSearch() {
      await runTimed("web_search", "searchButton", async () => requestJson("/api/web/search", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query: document.getElementById("query").value})
      }));
    }

    async function webRead() {
      await runTimed("web_read", "webReadButton", async () => requestJson("/api/web/read", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url: document.getElementById("webReadUrl").value})
      }));
    }

    async function agentReboot() {
      await runTimed("agent_reboot", "agentRebootButton", async () => requestJson("/api/agent/reboot", {method: "POST"}));
    }

    async function fullRestart() {
      await runTimed("full_restart", "fullRestartButton", async () => requestJson("/api/system/restart", {method: "POST"}));
    }

    async function refreshStyleAnchor() {
      await runTimed("style_anchor_refresh", "styleAnchorRefreshButton", async () => requestJson("/api/persona/style-anchor/refresh", {method: "POST"}));
    }

    async function exportStyleBundle() {
      await runTimed("style_bundle_export", "styleBundleExportButton", async () => requestJson("/api/persona/style-distillation/export", {method: "POST"}));
    }

    function bootDebugPage() {
      const savedTab = window.localStorage.getItem("debug-active-tab") || "overview";
      activateTab(savedTab);
      updateSettingLabels();
      updateSocialLabels();
      updateMemoryLabels();
      loadStatus();
      loadGlobalSocialState();
      loadSocialUsers();
      remoteDebugStatus();
      debugChatStatus();
      refreshLoopActivity();
      refreshDebugTimeline();
      window.setInterval(refreshLoopActivity, 1000);
      window.setInterval(refreshTopStatus, 3000);
    }

    bootDebugPage();
  </script>
</body>
</html>
"""
