const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const statusUrl = document.getElementById("status-url");
const metaWs = document.getElementById("meta-ws");
const metaRpc = document.getElementById("meta-rpc");
const metaRun = document.getElementById("meta-run");
const metaEventsTotal = document.getElementById("meta-events-total");

let eventsTotal = 0;
let ws;

function appendMessage(kind, text, meta) {
  if (!text) return;
  const wrapper = document.createElement("div");
  wrapper.className = `msg ${kind === "user" ? "msg-user" : "msg-assistant"}`;

  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "msg-meta";
    metaEl.textContent = meta;
    wrapper.appendChild(metaEl);
  }

  const body = document.createElement("div");
  body.textContent = text;
  wrapper.appendChild(body);
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setWsStatus(connected) {
  if (connected) {
    statusDot.classList.remove("err");
    statusDot.classList.add("ok");
    statusLabel.textContent = "CONNECTED";
    metaWs.textContent = "Connected";
  } else {
    statusDot.classList.remove("ok");
    statusDot.classList.add("err");
    statusLabel.textContent = "DISCONNECTED";
    metaWs.textContent = "Not connected";
  }
}

function init() {
  const loc = window.location;
  const baseHttp = `${loc.protocol}//${loc.host}`;
  const wsUrl = `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/ws`;
  const rpcUrl = `${baseHttp}/rpc`;

  statusUrl.textContent = baseHttp;
  metaRpc.textContent = "/rpc";

  setWsStatus(false);

  ws = new WebSocket(wsUrl);
  ws.addEventListener("open", () => {
    setWsStatus(true);
  });
  ws.addEventListener("close", () => {
    setWsStatus(false);
  });
  ws.addEventListener("error", () => {
    setWsStatus(false);
  });
  ws.addEventListener("message", (event) => {
    eventsTotal += 1;
    metaEventsTotal.textContent = String(eventsTotal);
    try {
      const payload = JSON.parse(event.data);
      const { run_id: runId, stream, data } = payload;
      if (runId) {
        metaRun.textContent = runId;
      }
      if (stream === "assistant" && data) {
        const text = data.text || data.delta || "";
        if (text) {
          appendMessage("assistant", text, runId ? `assistant · run ${runId}` : "assistant");
        }
      }
    } catch {
      // ignore malformed events
    }
  });

  sendBtn.addEventListener("click", async () => {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    appendMessage("user", text, "you");

    const idem = `dashboard-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const body = {
      id: idem,
      method: "agent",
      params: {
        message: text,
        sessionKey: "dashboard",
        sessionId: "dashboard",
        agentId: "dashboard",
        idempotencyKey: idem,
        channel: "dashboard",
      },
    };

    try {
      await fetch(rpcUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      appendMessage("assistant", `RPC error: ${err}`, "error");
    }
  });

  inputEl.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendBtn.click();
    }
  });
}

init();

