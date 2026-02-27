# Panther Live Automation
## Bridging Voice Conversation with Task Execution

---

## Overview

Panther Live is the real-time conversational layer of the Panther ecosystem. While it excels at live voice/text conversations, it currently lacks the ability to execute tasks such as browser automation, file operations, or system commands. This document outlines a robust architecture that enables Panther Live to delegate tasks to Panther Chat (which has full access to 100+ LLMs and browser automation tools) through a real-time bidirectional bridge — making Panther Live a fully capable assistant, not just a conversational one.

---

## The Core Problem

| Capability | Panther Chat | Panther Live |
|---|---|---|
| Multi-LLM Orchestration | ✅ | ✅ (limited) |
| Browser Automation | ✅ | ❌ |
| Task Execution | ✅ | ❌ |
| Real-time Conversation | Partial | ✅ |
| Voice Interaction | ❌ | ✅ |

Panther Live can talk but cannot act. Panther Chat can act but is not real-time conversational. The solution is a **Task Delegation Bridge** that lets them work as one unified system.

---

## Architecture: The Task Delegation Bridge

### High-Level Flow

```
User (Voice/Text)
      │
      ▼
┌─────────────┐       Task Request (JSON)      ┌──────────────┐
│             │ ─────────────────────────────► │              │
│  Panther    │                                │  Panther     │
│   Live      │                                │   Chat       │
│             │ ◄───────────────────────────── │              │
└─────────────┘       Task Result (JSON)       └──────────────┘
      │
      ▼
User gets response
("YouTube has been opened successfully")
```

### Bridge Communication Options

There are three viable bridge mechanisms. The recommended approach is **WebSocket** for real-time needs, with a fallback to **REST API** for simpler deployments.

#### Option 1 — WebSocket Bridge (Recommended)
A persistent, low-latency bidirectional socket connection between Panther Live and Panther Chat. Best for live conversations where users expect near-instant feedback.

#### Option 2 — Internal REST API
Panther Live makes an HTTP POST request to a Panther Chat internal endpoint. Panther Chat executes the task and responds. Simple, stateless, and easy to implement.

#### Option 3 — Message Queue (Redis / RabbitMQ)
Panther Live pushes a task to a queue. Panther Chat consumes it, executes, and pushes the result back to a response queue. Best for high-load production environments with many concurrent users.

---

## Detailed Step-by-Step Flow

### Step 1 — Intent Detection in Panther Live

When a user says something to Panther Live, an NLP/LLM-based **Intent Classifier** runs first to determine whether the user wants:

- A **conversational response** → handled locally by Panther Live
- A **task execution** → handed off to Panther Chat via the bridge

**Example intent classification:**

```json
{
  "user_input": "Open YouTube",
  "detected_intent": "BROWSER_OPEN",
  "confidence": 0.97,
  "requires_task_delegation": true
}
```

The classifier is universal — it is not hardcoded for YouTube or any specific site. It recognizes patterns like:
- *"Open [X]"*
- *"Go to [X]"*
- *"Search for [X] on the web"*
- *"Launch [X]"*
- *"Show me [X]"*
- *"Browse [X]"*

---

### Step 2 — Task Packet Construction

Panther Live builds a structured **Task Packet** and sends it to Panther Chat via the bridge.

```json
{
  "task_id": "plive_20240315_0042",
  "source": "panther_live",
  "session_id": "user_session_abc123",
  "task_type": "BROWSER_AUTOMATION",
  "action": "OPEN_URL",
  "parameters": {
    "target": "youtube.com",
    "resolved_url": "https://www.youtube.com",
    "user_raw_input": "Open YouTube"
  },
  "priority": "high",
  "timeout_ms": 10000,
  "callback_channel": "ws://internal/panther-live/session/abc123"
}
```

The `target` field is resolved universally — whether the user says "YouTube", "the Google homepage", "Reddit", "my email", or any URL, a **Universal Target Resolver** converts it to a concrete URL or system command.

---

### Step 3 — Universal Target Resolver

This is the critical component that makes the system universal and not limited to specific websites.

```
User Input ──► NLP Extraction ──► Target Resolver ──► Resolved Action
"Open YouTube"      "YouTube"      youtube.com        https://www.youtube.com
"Go to Reddit"      "Reddit"       reddit.com         https://www.reddit.com
"Open my Gmail"     "Gmail"        gmail.com          https://mail.google.com
"Search cats"       "cats"         google search      https://www.google.com/search?q=cats
"Open Spotify app"  "Spotify"      app://spotify      launch desktop app
"Open Downloads"    "Downloads"    file_system        open ~/Downloads folder
```

The resolver uses a combination of:
1. **Known Domain Mapping** — a curated list of popular services to URLs
2. **LLM Inference** — for ambiguous or novel targets, an LLM resolves the best match
3. **Web Search Fallback** — if uncertain, searches for the target and opens the top result
4. **App Detection** — checks if a desktop app exists before falling back to browser

---

### Step 4 — Panther Chat Executes the Task

Panther Chat receives the Task Packet, selects the appropriate automation agent (browser, file system, app launcher, etc.), and executes the task.

```
Panther Chat receives task_id: plive_20240315_0042
  → Identifies task_type: BROWSER_AUTOMATION
  → Calls Browser Automation Agent
  → Agent opens: https://www.youtube.com
  → Waits for page load confirmation
  → Captures result: SUCCESS / FAILURE
  → Records screenshot (optional, for verification)
```

Panther Chat's browser automation engine handles:
- Opening any URL
- Searching on any website
- Filling forms
- Clicking elements
- Scrolling and navigation
- Taking screenshots as proof of execution

---

### Step 5 — Result Sent Back to Panther Live

Panther Chat sends the result back to Panther Live through the same bridge channel.

```json
{
  "task_id": "plive_20240315_0042",
  "status": "SUCCESS",
  "executed_action": "Opened https://www.youtube.com",
  "execution_time_ms": 1842,
  "verification": {
    "page_title": "YouTube",
    "page_loaded": true,
    "screenshot_ref": "task_snap_0042.png"
  },
  "message_for_user": "YouTube has been opened successfully."
}
```

If the task fails, a reason is included:
```json
{
  "task_id": "plive_20240315_0043",
  "status": "FAILED",
  "reason": "Target URL unreachable. No internet connection detected.",
  "message_for_user": "I tried to open YouTube, but it seems there's no internet connection right now."
}
```

---

### Step 6 — Panther Live Responds to the User

Panther Live takes the `message_for_user` field and delivers it as a natural voice or text response to the user, completing the loop.

> *"YouTube has been opened successfully."*
> *"I tried to open that, but there's no internet connection right now."*

---

## Universal Task Types Supported

The bridge is not limited to opening websites. It supports a wide range of task categories:

| Task Category | Example User Input | Action Taken |
|---|---|---|
| Open Website | "Open YouTube" | Launches browser to youtube.com |
| Web Search | "Search for Python tutorials" | Google search query |
| Open App | "Open Spotify" | Launches desktop application |
| File System | "Open Downloads folder" | Opens file explorer |
| Media Control | "Play lofi music on YouTube" | Opens YouTube with search query |
| System Command | "Take a screenshot" | Executes system screenshot |
| Email | "Open my Gmail" | Navigates to mail.google.com |
| Social Media | "Go to my Twitter" | Opens twitter.com |
| Docs / Tools | "Open Google Docs" | Opens docs.google.com |
| Custom URL | "Go to github.com/panther" | Direct URL navigation |

---

## Implementation Blueprint

### Technology Stack Recommendation

```
Panther Live (Frontend / Voice Layer)
  └── WebSocket Client
  └── Intent Classifier (LLM-based, lightweight)
  └── Universal Target Resolver module

Bridge Layer
  └── WebSocket Server (Node.js / FastAPI)
  └── Task Queue (Redis for production)
  └── Session Manager

Panther Chat (Backend / Execution Layer)
  └── Task Router
  └── Browser Automation Agent (Playwright / Puppeteer / Selenium)
  └── App Launcher Agent
  └── File System Agent
  └── Result Verifier
  └── Response Formatter
```

### Simplified WebSocket Bridge (Pseudocode)

```python
# Panther Live Side — sending a task
async def delegate_task_to_chat(user_input, session_id):
    intent = classify_intent(user_input)
    
    if intent.requires_delegation:
        task_packet = build_task_packet(intent, session_id)
        await websocket.send(json.dumps(task_packet))
        
        result = await websocket.receive()
        result_data = json.loads(result)
        
        speak_to_user(result_data["message_for_user"])
    else:
        respond_conversationally(user_input)

# Panther Chat Side — receiving and executing
async def handle_task(task_packet):
    task = json.loads(task_packet)
    
    if task["task_type"] == "BROWSER_AUTOMATION":
        result = await browser_agent.execute(task["parameters"])
    elif task["task_type"] == "APP_LAUNCH":
        result = await app_agent.execute(task["parameters"])
    elif task["task_type"] == "FILE_SYSTEM":
        result = await file_agent.execute(task["parameters"])
    
    await websocket.send(json.dumps(format_result(result, task["task_id"])))
```

---

## Handling Edge Cases

### Ambiguous Commands
If a user says *"Open that thing we talked about earlier"*, Panther Live passes the conversation context along with the task packet so Panther Chat can resolve the reference correctly.

### Multiple Tasks in One Request
*"Open YouTube and search for lofi music"* is broken into a **task chain** — two sequential task packets are sent, and Panther Live waits for both confirmations before responding.

### Task Timeout
If Panther Chat does not respond within the defined `timeout_ms`, Panther Live informs the user that the task is taking longer than expected and optionally retries.

### Offline / Bridge Failure
If the bridge itself is down, Panther Live falls back to a graceful message: *"I'm not able to perform tasks right now, but I can still have a conversation with you."*

---

## Security Considerations

- All communication between Panther Live and Panther Chat happens over an **encrypted internal channel** (WSS / HTTPS) — never exposed to the public internet.
- Each task packet includes a **session token** to prevent unauthorized task injection.
- A **task allowlist/denylist** can be configured — for example, blocking system-level destructive commands.
- All executed tasks are **logged with user session IDs** for auditability.

---

## Summary

The Panther Live Automation bridge transforms Panther Live from a conversational-only interface into a fully capable assistant. By detecting task intent, constructing universal task packets, delegating execution to Panther Chat, and receiving verified results — all within a real-time WebSocket bridge — users get the best of both worlds: the natural, fluid conversation of Panther Live and the powerful task execution engine of Panther Chat.

The system is intentionally **universal and not hardcoded** to any specific website or application. Any target a user mentions — whether it's YouTube, a random URL, a desktop app, or a file folder — is resolved, executed, verified, and reported back to the user seamlessly.

---

*Document Version: 1.0 | Project: Panther | Component: Panther Live Automation Bridge*
