# NVIDIA AI Agent - Production Blueprint
## Speech-to-Speech, Browser-Enabled, Context-Aware AI Assistant

---

## 📋 Table of Contents

1. [Executive Overview](#executive-overview)
2. [Architecture Design](#architecture-design)
3. [Technical Stack](#technical-stack)
4. [Core Components](#core-components)
5. [Implementation Workflow](#implementation-workflow)
6. [UI/UX Design](#uiux-design)
7. [Security & Privacy](#security--privacy)
8. [Deployment Strategy](#deployment-strategy)
9. [Code Examples](#code-examples)

---

## Executive Overview

### Project Vision
A production-ready, native Python desktop application that leverages NVIDIA's AI models (DeepSeek Kimi, etc.) to provide an intelligent assistant with:
- Speech-to-speech interaction
- Browser automation capabilities
- Folder/file system access with permissions
- Long-term persistent memory
- Deep research and reasoning capabilities
- Professional UI similar to Claude Cowork

### Key Differentiators
- **Native Performance**: Built with Python + Qt for responsive desktop experience
- **Model Flexibility**: Support for multiple NVIDIA NIM models
- **Privacy-First**: Local memory storage with encryption
- **Extensible**: Plugin architecture for future capabilities

---

## Architecture Design

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERFACE LAYER                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Qt Main    │  │   Speech     │  │   Settings   │     │
│  │   Window     │  │   Interface  │  │   Manager    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CORE AGENT LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Agent      │  │   Memory     │  │   Task       │     │
│  │   Orchestr.  │  │   System     │  │   Planner    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CAPABILITY LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Browser    │  │   File       │  │   Research   │     │
│  │   Control    │  │   System     │  │   Engine     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    INTEGRATION LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   NVIDIA     │  │   Speech     │  │   Storage    │     │
│  │   NIM API    │  │   Services   │  │   Layer      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Architecture

```
Speech Input → STT → Text → Agent Processing → LLM (NVIDIA) →
                                                      ↓
                                              Response + Actions
                                                      ↓
                                        ┌─────────────┴────────────┐
                                        ▼                          ▼
                                  TTS → Speech          Browser/File Actions
                                                              ↓
                                                        Feedback Loop
```

---

## Technical Stack

### Core Technologies

#### Backend
- **Language**: Python 3.11+
- **API Client**: `httpx` (async NVIDIA API calls)
- **Database**: SQLite + `sqlalchemy` (memory persistence)
- **Vector Store**: `chromadb` (semantic memory)
- **Task Queue**: `asyncio` + `aiofiles`

#### UI Framework
- **Primary**: PyQt6 or PySide6 (native performance)
- **Alternative**: CustomTkinter (lighter weight)
- **Icons**: Phosphor Icons or Material Icons
- **Styling**: QSS (Qt Style Sheets)

#### Speech Capabilities
- **STT**: 
  - Primary: `faster-whisper` (local, fast)
  - Fallback: `openai-whisper`
- **TTS**:
  - Primary: `piper-tts` (local, high quality)
  - Alternative: `coqui-tts`, `elevenlabs-api`
- **Audio**: `pyaudio`, `sounddevice`

#### Browser Automation
- **Primary**: `playwright` (modern, reliable)
- **Alternative**: `selenium` (broader compatibility)
- **Screenshot**: `pillow`, `mss`

#### File System
- **Access**: `watchdog` (file monitoring)
- **Permissions**: OS-level permissions + custom ACL
- **Search**: `whoosh` (full-text indexing)

#### AI/ML Libraries
- **NLP**: `spacy`, `nltk` (text processing)
- **Embeddings**: `sentence-transformers`
- **Reasoning**: Custom prompt engineering

### Development Tools
- **Package Manager**: `poetry` or `pip-tools`
- **Testing**: `pytest`, `pytest-asyncio`
- **Logging**: `loguru`
- **Config**: `pydantic-settings`
- **CLI**: `typer` (for dev tools)

---

## Core Components

### 1. API Manager

**Purpose**: Handle all NVIDIA API interactions with retry logic, rate limiting, and key management.

**Key Features**:
- Secure API key storage (OS keyring)
- Model selection and switching
- Token counting and budget management
- Response streaming
- Error handling and fallbacks

**Class Structure**:
```python
class NVIDIAAPIManager:
    - api_key: str
    - base_url: str
    - model: str
    - client: httpx.AsyncClient
    
    + initialize(api_key: str)
    + chat_completion(messages: List[Dict], stream: bool)
    + validate_key() -> bool
    + list_models() -> List[str]
    + get_token_usage() -> Dict
```

### 2. Memory System

**Purpose**: Persistent, searchable memory with semantic understanding.

**Architecture**:
```
┌─────────────────────────────────────────────┐
│           Memory System                     │
│  ┌──────────────────┐  ┌────────────────┐  │
│  │  Short-term      │  │  Long-term     │  │
│  │  (Session)       │  │  (Persistent)  │  │
│  └──────────────────┘  └────────────────┘  │
│           │                     │           │
│           └─────────┬───────────┘           │
│                     ▼                       │
│           ┌──────────────────┐              │
│           │  Vector Store    │              │
│           │  (Semantic       │              │
│           │   Search)        │              │
│           └──────────────────┘              │
└─────────────────────────────────────────────┘
```

**Components**:
- **Conversation Memory**: Store all interactions
- **Document Memory**: Remember accessed files/folders
- **Task Memory**: Track completed and pending tasks
- **Preference Memory**: User preferences and patterns
- **Semantic Search**: Find relevant memories by meaning

**Database Schema**:
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT,
    timestamp DATETIME,
    metadata JSON
);

CREATE TABLE memories (
    id INTEGER PRIMARY KEY,
    memory_type TEXT,
    content TEXT,
    embedding BLOB,
    importance INTEGER,
    timestamp DATETIME,
    metadata JSON
);

CREATE TABLE file_access_history (
    id INTEGER PRIMARY KEY,
    file_path TEXT,
    action TEXT,
    timestamp DATETIME,
    summary TEXT
);
```

### 3. Agent Orchestrator

**Purpose**: Central brain that coordinates all capabilities.

**Responsibilities**:
- Parse user intent
- Plan multi-step tasks
- Coordinate between subsystems
- Manage execution flow
- Handle errors and retries

**Decision Tree**:
```
User Input
    │
    ├─→ Is Speech? → STT Processing
    │
    ├─→ Analyze Intent
    │       │
    │       ├─→ Simple Query → Direct LLM Response
    │       │
    │       ├─→ File Operation → File System Handler
    │       │
    │       ├─→ Browser Task → Browser Automation
    │       │
    │       ├─→ Research → Deep Research Engine
    │       │
    │       └─→ Complex Task → Task Planner
    │
    └─→ Execute & Monitor → Feedback Loop
```

### 4. Browser Controller

**Purpose**: Automate browser interactions for web tasks.

**Capabilities**:
- Page navigation
- Element interaction (click, type, scroll)
- Content extraction
- Screenshot capture
- Multi-tab management
- Cookie/session handling

**Safety Features**:
- URL whitelist/blacklist
- Sensitive action confirmation
- Session isolation
- Privacy mode

**Example Workflow**:
```python
class BrowserController:
    - playwright_browser
    - active_pages: Dict[str, Page]
    
    + navigate(url: str, page_id: str)
    + click(selector: str, page_id: str)
    + extract_content(selector: str) -> str
    + fill_form(data: Dict, page_id: str)
    + take_screenshot() -> bytes
    + wait_for_element(selector: str, timeout: int)
```

### 5. File System Manager

**Purpose**: Secure, permission-based file/folder access.

**Features**:
- Permission management (user-granted access)
- File indexing and search
- Real-time monitoring
- Metadata extraction
- Diff tracking

**Permission Model**:
```python
class FilePermission:
    - path: str
    - permission_type: Enum (READ, WRITE, EXECUTE)
    - granted_at: datetime
    - expires_at: Optional[datetime]
    - recursive: bool
```

**Operations**:
- Read files
- Write/modify files
- Create directories
- Search within folders
- Monitor for changes
- Extract text from documents

### 6. Speech Interface

**Purpose**: Enable natural voice interaction.

**Pipeline**:
```
Microphone Input
    ↓
Audio Processing (noise reduction, VAD)
    ↓
STT (faster-whisper)
    ↓
Text Processing
    ↓
Agent Response
    ↓
TTS (piper-tts)
    ↓
Audio Output
```

**Features**:
- Voice activity detection (VAD)
- Wake word detection (optional)
- Speaker diarization
- Emotion detection
- Multi-language support

### 7. Research Engine

**Purpose**: Deep research with source verification.

**Process**:
```
Research Query
    ↓
Query Decomposition (break into sub-questions)
    ↓
Parallel Research (multiple searches)
    ↓
Source Evaluation (credibility scoring)
    ↓
Information Synthesis
    ↓
Fact Verification
    ↓
Report Generation with Citations
```

**Components**:
- Search query generator
- Web scraper (respects robots.txt)
- Source credibility analyzer
- Content summarizer
- Citation manager

---

## Implementation Workflow

### Phase 1: Foundation (Weeks 1-2)

#### Week 1: Project Setup
```bash
# Day 1-2: Environment Setup
1. Initialize project structure
2. Set up poetry/pip-tools
3. Create virtual environment
4. Configure pre-commit hooks
5. Set up logging system

# Day 3-4: Core API Integration
1. Implement NVIDIA API client
2. Add key storage (keyring)
3. Create model selection logic
4. Test API connectivity
5. Implement error handling

# Day 5-7: Basic UI Framework
1. Create Qt6 main window
2. Implement settings dialog
3. Add API key input interface
4. Create chat interface
5. Add basic styling
```

#### Week 2: Core Capabilities
```bash
# Day 1-3: Memory System
1. Design database schema
2. Implement SQLite connection
3. Create conversation storage
4. Add vector embedding (ChromaDB)
5. Implement semantic search

# Day 4-5: Agent Orchestrator
1. Create agent core logic
2. Implement intent classification
3. Add task planning
4. Create execution manager
5. Add feedback loop

# Day 6-7: Testing & Integration
1. Unit tests for core components
2. Integration tests
3. Performance optimization
4. Documentation
```

### Phase 2: Advanced Features (Weeks 3-4)

#### Week 3: Browser & Files
```bash
# Day 1-3: Browser Controller
1. Set up Playwright
2. Implement navigation
3. Add element interaction
4. Create screenshot capture
5. Test web automation

# Day 4-5: File System Manager
1. Implement permission system
2. Add file reading/writing
3. Create file search
4. Add monitoring
5. Test security

# Day 6-7: Integration
1. Connect browser to agent
2. Connect files to agent
3. Test workflows
4. Bug fixes
```

#### Week 4: Speech & Research
```bash
# Day 1-3: Speech Interface
1. Integrate faster-whisper (STT)
2. Integrate piper-tts (TTS)
3. Add voice activity detection
4. Create audio pipeline
5. Test end-to-end speech

# Day 4-5: Research Engine
1. Create search logic
2. Implement web scraping
3. Add synthesis
4. Create citation manager
5. Test research workflows

# Day 6-7: Polish & Testing
1. Full system integration
2. End-to-end testing
3. Performance tuning
4. Bug fixes
```

### Phase 3: Production Ready (Weeks 5-6)

#### Week 5: Polish & Security
```bash
# Day 1-3: UI/UX Polish
1. Refine interface design
2. Add animations
3. Improve responsiveness
4. Add dark mode
5. User testing

# Day 4-5: Security Hardening
1. Input validation
2. API key encryption
3. Sandbox file operations
4. Audit logging
5. Security testing

# Day 6-7: Documentation
1. User manual
2. API documentation
3. Developer guide
4. Video tutorials
```

#### Week 6: Deployment
```bash
# Day 1-3: Packaging
1. Create installers (Windows/Mac/Linux)
2. Code signing
3. Auto-update system
4. Crash reporting
5. Analytics (privacy-respecting)

# Day 4-5: Release Prep
1. Final testing
2. Beta release
3. Gather feedback
4. Bug fixes

# Day 6-7: Launch
1. Public release
2. Marketing materials
3. Community setup
4. Support system
```

---

## UI/UX Design

### Main Window Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  NVIDIA AI Agent                                    [_] [□] [×] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────┐  ┌──────────────────────────────────────────┐  │
│  │            │  │                                          │  │
│  │  SIDEBAR   │  │         MAIN CHAT AREA                  │  │
│  │            │  │                                          │  │
│  │  • Chat    │  │  [AI Message]                           │  │
│  │  • Files   │  │  [User Message]                         │  │
│  │  • Browser │  │  [AI Message with Actions]              │  │
│  │  • Memory  │  │                                          │  │
│  │  • Tasks   │  │                                          │  │
│  │  • Settings│  │                                          │  │
│  │            │  │                                          │  │
│  │            │  │                                          │  │
│  │            │  │                                          │  │
│  └────────────┘  └──────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  [🎤] Type a message or hold to speak...         [Send]  │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Color Scheme (Dark Theme Default)

```python
COLORS = {
    "background": "#1a1a1a",
    "surface": "#2d2d2d",
    "surface_variant": "#3d3d3d",
    "primary": "#76b900",  # NVIDIA green
    "secondary": "#00d4aa",
    "text": "#ffffff",
    "text_secondary": "#b0b0b0",
    "border": "#404040",
    "error": "#ff5252",
    "success": "#4caf50",
    "warning": "#ffc107"
}
```

### Key UI Components

#### 1. Chat Interface
- **Message Bubbles**: Rounded corners, shadows
- **Code Blocks**: Syntax highlighting, copy button
- **Actions**: Inline buttons for file/browser operations
- **Streaming**: Real-time text generation
- **Rich Media**: Images, files, links preview

#### 2. Settings Panel
```
┌─────────────────────────────────────────┐
│  Settings                               │
├─────────────────────────────────────────┤
│                                         │
│  API Configuration                      │
│  ┌─────────────────────────────────┐   │
│  │ NVIDIA API Key: ********        │   │
│  └─────────────────────────────────┘   │
│  [Test Connection]                      │
│                                         │
│  Model Selection                        │
│  ┌─────────────────────────────────┐   │
│  │ ▼ nvidia/kimi-k-2.5             │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Speech Settings                        │
│  🔊 Volume: [=========>     ] 80%       │
│  🎙️ Microphone: [Default Device ▼]     │
│  ☑ Push to Talk                         │
│  ☑ Wake Word: "Hey Assistant"           │
│                                         │
│  Memory Settings                        │
│  Storage: 245 MB / 1 GB                 │
│  [Clear History] [Export]               │
│                                         │
│  Privacy                                │
│  ☑ Local Processing                     │
│  ☐ Send Analytics                       │
│  ☑ Encrypt Storage                      │
│                                         │
└─────────────────────────────────────────┘
```

#### 3. File Browser Integration
```
┌─────────────────────────────────────────┐
│  Accessible Folders                     │
├─────────────────────────────────────────┤
│  📁 ~/Documents          [Access: RW]   │
│  📁 ~/Downloads          [Access: R]    │
│  📁 ~/Projects/AI        [Access: RWX]  │
│                                         │
│  [+ Add Folder]                         │
└─────────────────────────────────────────┘
```

#### 4. Browser Status
```
┌─────────────────────────────────────────┐
│  Browser Activity                       │
├─────────────────────────────────────────┤
│  🌐 Tab 1: Google Search                │
│     Status: Waiting for element         │
│                                         │
│  🌐 Tab 2: GitHub                       │
│     Status: Logged in                   │
│                                         │
│  [🔍 View Screenshots]                  │
└─────────────────────────────────────────┘
```

### Interaction Patterns

#### Voice Interaction
1. **Push-to-Talk**: Hold Ctrl+Space to speak
2. **Wake Word**: Say "Hey Assistant" to activate
3. **Visual Feedback**: Waveform animation during speech
4. **Interrupt**: Tap to stop agent from speaking

#### Task Management
```
Current Task: "Research latest AI papers and summarize"

Steps:
  ✓ 1. Search arXiv for papers (completed)
  ⟳ 2. Extract abstracts (in progress)
  ○ 3. Analyze with LLM (pending)
  ○ 4. Generate summary (pending)

[Pause] [Cancel]
```

---

## Security & Privacy

### Security Layers

#### 1. API Key Protection
```python
# Use OS keyring for secure storage
import keyring

def store_api_key(key: str):
    keyring.set_password("nvidia_ai_agent", "api_key", key)

def get_api_key() -> str:
    return keyring.get_password("nvidia_ai_agent", "api_key")
```

#### 2. File System Sandboxing
- Explicit user permission for each folder
- Read-only by default
- Whitelist approach
- Audit logging of all file operations

```python
class FilePermissionManager:
    def request_permission(self, path: str, access_type: str):
        # Show OS-level permission dialog
        # Log request
        # Store in database if granted
        pass
    
    def check_permission(self, path: str, access_type: str) -> bool:
        # Verify against stored permissions
        # Check if expired
        # Return boolean
        pass
```

#### 3. Browser Isolation
- Separate browser profile per session
- No persistent cookies
- Private browsing mode
- URL filtering

#### 4. Data Encryption
```python
from cryptography.fernet import Fernet

class EncryptedStorage:
    def __init__(self):
        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)
    
    def encrypt(self, data: bytes) -> bytes:
        return self.cipher.encrypt(data)
    
    def decrypt(self, data: bytes) -> bytes:
        return self.cipher.decrypt(data)
```

### Privacy Features

1. **Local Processing**: All speech processing happens locally
2. **No Telemetry**: Optional analytics, disabled by default
3. **Data Retention**: User-configurable memory deletion
4. **Export Control**: Users can export/delete all their data
5. **Transparent Logging**: All API calls logged with consent

### Compliance Considerations

- **GDPR**: Right to erasure, data portability
- **CCPA**: User consent, data access
- **SOC 2**: Audit trails, access controls
- **HIPAA**: (If handling medical data) Encryption, logging

---

## Deployment Strategy

### Build System

#### Requirements
```toml
# pyproject.toml
[tool.poetry]
name = "nvidia-ai-agent"
version = "1.0.0"
description = "Production AI Agent with NVIDIA NIM"

[tool.poetry.dependencies]
python = "^3.11"
PyQt6 = "^6.6.0"
httpx = "^0.25.0"
faster-whisper = "^0.10.0"
piper-tts = "^1.2.0"
playwright = "^1.40.0"
chromadb = "^0.4.18"
sqlalchemy = "^2.0.23"
watchdog = "^3.0.0"
loguru = "^0.7.2"
pydantic = "^2.5.0"
keyring = "^24.3.0"
```

### Packaging

#### Windows (PyInstaller)
```bash
pyinstaller --name "NVIDIA AI Agent" \
            --windowed \
            --icon=assets/icon.ico \
            --add-data "models:models" \
            --add-data "assets:assets" \
            --hidden-import=piper_tts \
            --hidden-import=faster_whisper \
            main.py
```

#### macOS (py2app)
```bash
python setup.py py2app \
    --iconfile=assets/icon.icns \
    --packages=PyQt6,chromadb
```

#### Linux (AppImage)
```bash
# Create AppDir structure
# Bundle dependencies
# Generate AppImage
appimagetool nvidia-ai-agent.AppDir
```

### Auto-Update System

```python
class UpdateManager:
    def check_for_updates(self) -> Optional[str]:
        # Check GitHub releases
        # Compare versions
        # Return download URL if newer
        pass
    
    def download_update(self, url: str):
        # Download new version
        # Verify signature
        # Prepare for installation
        pass
    
    def apply_update(self):
        # Backup current version
        # Install new version
        # Restart application
        pass
```

### Distribution Channels

1. **GitHub Releases**: Primary distribution
2. **Website**: Direct downloads
3. **Package Managers**:
   - Windows: Winget, Chocolatey
   - macOS: Homebrew
   - Linux: Snap, Flatpak

---

## Code Examples

### 1. Main Application Entry Point

```python
# main.py
import sys
import asyncio
from PyQt6.QtWidgets import QApplication
from PyQt6.QtAsyncio import QAsyncioEventLoopPolicy
from loguru import logger

from src.ui.main_window import MainWindow
from src.core.agent import AgentOrchestrator
from src.config import load_config

async def main():
    logger.info("Starting NVIDIA AI Agent")
    
    # Load configuration
    config = load_config()
    
    # Initialize Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("NVIDIA AI Agent")
    app.setStyle("Fusion")
    
    # Apply dark theme
    from src.ui.themes import apply_dark_theme
    apply_dark_theme(app)
    
    # Initialize Agent Orchestrator
    orchestrator = AgentOrchestrator(config)
    await orchestrator.initialize()
    
    # Create main window
    window = MainWindow(orchestrator)
    window.show()
    
    # Run event loop
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Use Qt's asyncio policy for async/await support
    asyncio.set_event_loop_policy(QAsyncioEventLoopPolicy())
    asyncio.run(main())
```

### 2. NVIDIA API Client

```python
# src/api/nvidia_client.py
import httpx
from typing import AsyncIterator, Dict, List, Optional
from loguru import logger

class NVIDIAClient:
    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=300.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "nvidia/kimi-k-2.5",
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> AsyncIterator[str]:
        """
        Send chat completion request to NVIDIA NIM API.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        
        Yields:
            Response chunks if streaming, else full response
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        logger.info(f"Sending request to {model} (stream={stream})")
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload
            ) as response:
                response.raise_for_status()
                
                if stream:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            
                            import json
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                else:
                    data = await response.json()
                    yield data["choices"][0]["message"]["content"]
        
        except httpx.HTTPError as e:
            logger.error(f"API request failed: {e}")
            raise
    
    async def validate_api_key(self) -> bool:
        """Test if API key is valid."""
        try:
            messages = [{"role": "user", "content": "Hi"}]
            async for _ in self.chat_completion(messages, stream=False):
                return True
        except:
            return False
    
    async def list_models(self) -> List[str]:
        """Fetch available models."""
        response = await self.client.get(f"{self.base_url}/models")
        response.raise_for_status()
        data = response.json()
        return [model["id"] for model in data.get("data", [])]
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
```

### 3. Agent Orchestrator

```python
# src/core/agent.py
import asyncio
from typing import Dict, List, Optional
from loguru import logger

from src.api.nvidia_client import NVIDIAClient
from src.memory.memory_system import MemorySystem
from src.capabilities.browser import BrowserController
from src.capabilities.files import FileSystemManager
from src.capabilities.research import ResearchEngine

class AgentOrchestrator:
    def __init__(self, config):
        self.config = config
        self.nvidia_client: Optional[NVIDIAClient] = None
        self.memory = MemorySystem(config.db_path)
        self.browser = BrowserController()
        self.files = FileSystemManager()
        self.research = ResearchEngine()
        self.active_tasks: Dict[str, asyncio.Task] = {}
    
    async def initialize(self):
        """Initialize all subsystems."""
        logger.info("Initializing agent orchestrator")
        await self.memory.initialize()
        await self.browser.initialize()
    
    def set_api_key(self, api_key: str):
        """Set NVIDIA API key."""
        self.nvidia_client = NVIDIAClient(api_key)
    
    async def process_message(self, message: str) -> AsyncIterator[str]:
        """
        Main entry point for processing user messages.
        
        Args:
            message: User input text
        
        Yields:
            Response chunks
        """
        # Store in memory
        await self.memory.add_message("user", message)
        
        # Retrieve relevant context
        context = await self.memory.get_relevant_context(message, limit=5)
        
        # Build messages for LLM
        messages = self._build_messages(message, context)
        
        # Classify intent
        intent = await self._classify_intent(message)
        logger.info(f"Classified intent: {intent}")
        
        # Handle based on intent
        if intent == "file_operation":
            async for chunk in self._handle_file_operation(message, messages):
                yield chunk
        
        elif intent == "browser_task":
            async for chunk in self._handle_browser_task(message, messages):
                yield chunk
        
        elif intent == "research":
            async for chunk in self._handle_research(message, messages):
                yield chunk
        
        else:
            # Standard chat
            async for chunk in self._handle_chat(messages):
                yield chunk
    
    async def _classify_intent(self, message: str) -> str:
        """Classify user intent using small model or rules."""
        # Simple rule-based classification (can be enhanced with ML)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["open", "read", "file", "folder", "document"]):
            return "file_operation"
        
        if any(word in message_lower for word in ["browse", "website", "open browser", "navigate"]):
            return "browser_task"
        
        if any(word in message_lower for word in ["research", "search", "find information", "investigate"]):
            return "research"
        
        return "chat"
    
    def _build_messages(self, message: str, context: List[str]) -> List[Dict]:
        """Build message list with system prompt and context."""
        system_prompt = """You are an intelligent AI assistant with the following capabilities:
        - Access to files and folders (with permission)
        - Browser automation for web tasks
        - Deep research with source verification
        - Long-term memory of conversations and tasks
        
        Be helpful, concise, and proactive. When performing actions, explain what you're doing.
        """
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add relevant context
        if context:
            context_text = "\n\nRelevant context from memory:\n" + "\n".join(context)
            messages.append({"role": "system", "content": context_text})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        return messages
    
    async def _handle_chat(self, messages: List[Dict]) -> AsyncIterator[str]:
        """Handle standard chat interaction."""
        full_response = ""
        async for chunk in self.nvidia_client.chat_completion(messages):
            full_response += chunk
            yield chunk
        
        # Store response in memory
        await self.memory.add_message("assistant", full_response)
    
    async def _handle_file_operation(self, message: str, messages: List[Dict]) -> AsyncIterator[str]:
        """Handle file system operations."""
        # Ask LLM to plan file operations
        messages.append({
            "role": "system",
            "content": "Respond with a JSON object specifying the file operations needed."
        })
        
        response = ""
        async for chunk in self.nvidia_client.chat_completion(messages, stream=False):
            response = chunk
        
        # Parse and execute file operations
        # (Implement file operation logic here)
        
        yield f"Executing file operation: {response}\n"
        
        # Store in memory
        await self.memory.add_message("assistant", response)
    
    async def _handle_browser_task(self, message: str, messages: List[Dict]) -> AsyncIterator[str]:
        """Handle browser automation tasks."""
        yield "Launching browser...\n"
        
        # Plan browser actions
        messages.append({
            "role": "system",
            "content": "Respond with step-by-step browser actions needed."
        })
        
        plan = ""
        async for chunk in self.nvidia_client.chat_completion(messages, stream=False):
            plan = chunk
        
        yield f"Plan: {plan}\n"
        
        # Execute browser actions
        # (Implement browser automation logic)
        
        await self.memory.add_message("assistant", plan)
    
    async def _handle_research(self, message: str, messages: List[Dict]) -> AsyncIterator[str]:
        """Handle research tasks."""
        yield "Starting research...\n"
        
        # Use research engine
        results = await self.research.deep_research(message)
        
        # Synthesize with LLM
        messages.append({
            "role": "system",
            "content": f"Synthesize these research results:\n{results}"
        })
        
        async for chunk in self.nvidia_client.chat_completion(messages):
            yield chunk
        
        await self.memory.add_message("assistant", results)
```

### 4. Memory System

```python
# src/memory/memory_system.py
import sqlite3
from datetime import datetime
from typing import List, Optional
import chromadb
from chromadb.utils import embedding_functions
from loguru import logger

class MemorySystem:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.chroma_client: Optional[chromadb.Client] = None
        self.collection = None
    
    async def initialize(self):
        """Initialize database and vector store."""
        logger.info("Initializing memory system")
        
        # SQLite for structured data
        self.conn = sqlite3.connect(self.db_path)
        self._create_tables()
        
        # ChromaDB for semantic search
        self.chroma_client = chromadb.Client()
        
        # Use sentence transformers for embeddings
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.chroma_client.get_or_create_collection(
            name="conversations",
            embedding_function=embedding_fn
        )
    
    def _create_tables(self):
        """Create database schema."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                action TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                summary TEXT
            )
        """)
        
        self.conn.commit()
    
    async def add_message(self, role: str, content: str, session_id: str = "default"):
        """Store a conversation message."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        self.conn.commit()
        
        # Add to vector store for semantic search
        message_id = cursor.lastrowid
        self.collection.add(
            documents=[content],
            metadatas=[{"role": role, "timestamp": str(datetime.now())}],
            ids=[f"msg_{message_id}"]
        )
        
        logger.debug(f"Stored message: {role} - {content[:50]}...")
    
    async def get_relevant_context(self, query: str, limit: int = 5) -> List[str]:
        """Retrieve relevant context using semantic search."""
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        if results and results["documents"]:
            return results["documents"][0]
        return []
    
    async def get_recent_messages(self, limit: int = 10, session_id: str = "default") -> List[Dict]:
        """Get recent conversation history."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT role, content, timestamp FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        )
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row[0],
                "content": row[1],
                "timestamp": row[2]
            })
        
        return messages[::-1]  # Reverse to chronological order
    
    async def clear_session(self, session_id: str = "default"):
        """Clear a conversation session."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        self.conn.commit()
        logger.info(f"Cleared session: {session_id}")
```

### 5. Browser Controller

```python
# src/capabilities/browser.py
from playwright.async_api import async_playwright, Browser, Page
from typing import Dict, Optional
from loguru import logger

class BrowserController:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.pages: Dict[str, Page] = {}
    
    async def initialize(self):
        """Initialize Playwright browser."""
        logger.info("Initializing browser controller")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Show browser for transparency
            args=['--disable-blink-features=AutomationControlled']
        )
    
    async def new_page(self, page_id: str) -> Page:
        """Create a new browser page."""
        page = await self.browser.new_page()
        self.pages[page_id] = page
        logger.info(f"Created new page: {page_id}")
        return page
    
    async def navigate(self, url: str, page_id: str = "main"):
        """Navigate to a URL."""
        if page_id not in self.pages:
            await self.new_page(page_id)
        
        page = self.pages[page_id]
        await page.goto(url)
        logger.info(f"Navigated to: {url}")
    
    async def click(self, selector: str, page_id: str = "main"):
        """Click an element."""
        page = self.pages.get(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")
        
        await page.click(selector)
        logger.info(f"Clicked: {selector}")
    
    async def type_text(self, selector: str, text: str, page_id: str = "main"):
        """Type text into an input."""
        page = self.pages.get(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")
        
        await page.fill(selector, text)
        logger.info(f"Typed into {selector}")
    
    async def extract_text(self, selector: str, page_id: str = "main") -> str:
        """Extract text from element."""
        page = self.pages.get(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")
        
        element = await page.query_selector(selector)
        if element:
            return await element.inner_text()
        return ""
    
    async def screenshot(self, page_id: str = "main") -> bytes:
        """Take screenshot of page."""
        page = self.pages.get(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")
        
        return await page.screenshot()
    
    async def close_page(self, page_id: str):
        """Close a specific page."""
        if page_id in self.pages:
            await self.pages[page_id].close()
            del self.pages[page_id]
            logger.info(f"Closed page: {page_id}")
    
    async def shutdown(self):
        """Shutdown browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser shut down")
```

### 6. Speech Interface

```python
# src/capabilities/speech.py
import asyncio
from faster_whisper import WhisperModel
from piper import PiperVoice
import sounddevice as sd
import numpy as np
from loguru import logger

class SpeechInterface:
    def __init__(self):
        # STT with faster-whisper
        self.whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        
        # TTS with piper
        self.tts_voice = PiperVoice.load("en_US-lessac-medium")
        
        # Audio settings
        self.sample_rate = 16000
        self.channels = 1
    
    async def speech_to_text(self, audio_data: np.ndarray) -> str:
        """Convert speech to text using Whisper."""
        logger.info("Transcribing audio...")
        
        # Whisper expects float32
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        segments, info = self.whisper_model.transcribe(
            audio_float,
            beam_size=5,
            language="en"
        )
        
        text = " ".join([segment.text for segment in segments])
        logger.info(f"Transcription: {text}")
        return text.strip()
    
    async def text_to_speech(self, text: str) -> np.ndarray:
        """Convert text to speech using Piper."""
        logger.info(f"Synthesizing speech: {text[:50]}...")
        
        # Generate audio
        audio_data = []
        for audio_chunk in self.tts_voice.synthesize_stream_raw(text):
            audio_data.extend(audio_chunk)
        
        # Convert to numpy array
        audio_array = np.array(audio_data, dtype=np.int16)
        return audio_array
    
    def record_audio(self, duration: int = 5) -> np.ndarray:
        """Record audio from microphone."""
        logger.info(f"Recording for {duration} seconds...")
        
        recording = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.int16
        )
        sd.wait()
        
        return recording.flatten()
    
    def play_audio(self, audio_data: np.ndarray):
        """Play audio through speakers."""
        logger.info("Playing audio...")
        sd.play(audio_data, self.sample_rate)
        sd.wait()
    
    async def listen_and_transcribe(self, duration: int = 5) -> str:
        """Record and transcribe audio."""
        audio = self.record_audio(duration)
        text = await self.speech_to_text(audio)
        return text
    
    async def synthesize_and_play(self, text: str):
        """Synthesize and play speech."""
        audio = await self.text_to_speech(text)
        self.play_audio(audio)
```

---

## Advanced Features

### 1. Task Planner

```python
# src/core/task_planner.py
from typing import List, Dict
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Task:
    def __init__(self, description: str, steps: List[str]):
        self.description = description
        self.steps = steps
        self.current_step = 0
        self.status = TaskStatus.PENDING
        self.results: List[str] = []
    
    def next_step(self) -> Optional[str]:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None
    
    def complete_step(self, result: str):
        self.results.append(result)
        self.current_step += 1
        
        if self.current_step >= len(self.steps):
            self.status = TaskStatus.COMPLETED

class TaskPlanner:
    def __init__(self, nvidia_client):
        self.nvidia_client = nvidia_client
        self.active_tasks: Dict[str, Task] = {}
    
    async def plan_task(self, goal: str) -> Task:
        """Break down a complex goal into steps."""
        messages = [
            {
                "role": "system",
                "content": "You are a task planning assistant. Break down the user's goal into specific, actionable steps."
            },
            {
                "role": "user",
                "content": f"Goal: {goal}\n\nProvide a numbered list of steps to accomplish this goal."
            }
        ]
        
        plan_text = ""
        async for chunk in self.nvidia_client.chat_completion(messages, stream=False):
            plan_text = chunk
        
        # Parse steps (simple line-by-line parsing)
        steps = [line.strip() for line in plan_text.split('\n') if line.strip()]
        
        task = Task(goal, steps)
        return task
```

### 2. Research Engine

```python
# src/capabilities/research.py
import asyncio
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

class ResearchEngine:
    def __init__(self):
        self.client = httpx.AsyncClient()
    
    async def deep_research(self, query: str) -> str:
        """Perform deep research on a topic."""
        # Step 1: Generate sub-questions
        sub_queries = await self._generate_sub_questions(query)
        
        # Step 2: Search for each sub-question
        all_results = []
        for sub_query in sub_queries:
            results = await self._search_web(sub_query)
            all_results.extend(results)
        
        # Step 3: Extract and synthesize information
        synthesized = await self._synthesize_results(all_results, query)
        
        return synthesized
    
    async def _generate_sub_questions(self, query: str) -> List[str]:
        """Break query into sub-questions."""
        # Use LLM to generate sub-questions
        # Simplified for example
        return [query, f"recent developments in {query}"]
    
    async def _search_web(self, query: str) -> List[Dict]:
        """Search the web for query."""
        # Implement actual search (e.g., DuckDuckGo, Bing API)
        # Simplified for example
        return [
            {"url": "example.com", "title": "Example", "snippet": "..."}
        ]
    
    async def _synthesize_results(self, results: List[Dict], original_query: str) -> str:
        """Synthesize search results into coherent answer."""
        # Use LLM to synthesize
        # Simplified for example
        return f"Research results for: {original_query}\n\n" + "\n".join([r["snippet"] for r in results])
```

---

## Performance Optimization

### 1. Caching Strategy

```python
# src/utils/cache.py
from functools import lru_cache
import hashlib
import json

class ResponseCache:
    def __init__(self, max_size: int = 100):
        self.cache = {}
        self.max_size = max_size
    
    def get_key(self, messages: List[Dict]) -> str:
        """Generate cache key from messages."""
        content = json.dumps(messages, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, messages: List[Dict]) -> Optional[str]:
        """Get cached response."""
        key = self.get_key(messages)
        return self.cache.get(key)
    
    def set(self, messages: List[Dict], response: str):
        """Cache response."""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            self.cache.pop(next(iter(self.cache)))
        
        key = self.get_key(messages)
        self.cache[key] = response
```

### 2. Async Processing

```python
# Process multiple requests concurrently
async def process_batch(requests: List[str]):
    tasks = [agent.process_message(req) for req in requests]
    results = await asyncio.gather(*tasks)
    return results
```

### 3. Lazy Loading

```python
# Load heavy models only when needed
class LazyModel:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
    
    @property
    def model(self):
        if self._model is None:
            self._model = self._load_model()
        return self._model
    
    def _load_model(self):
        # Load actual model
        pass
```

---

## Testing Strategy

### 1. Unit Tests

```python
# tests/test_nvidia_client.py
import pytest
from src.api.nvidia_client import NVIDIAClient

@pytest.mark.asyncio
async def test_chat_completion():
    client = NVIDIAClient(api_key="test_key")
    messages = [{"role": "user", "content": "Hello"}]
    
    response = ""
    async for chunk in client.chat_completion(messages):
        response += chunk
    
    assert len(response) > 0

@pytest.mark.asyncio
async def test_api_key_validation():
    client = NVIDIAClient(api_key="invalid_key")
    is_valid = await client.validate_api_key()
    assert is_valid == False
```

### 2. Integration Tests

```python
# tests/test_agent_integration.py
import pytest
from src.core.agent import AgentOrchestrator

@pytest.mark.asyncio
async def test_full_conversation():
    agent = AgentOrchestrator(config)
    await agent.initialize()
    agent.set_api_key("test_key")
    
    response = ""
    async for chunk in agent.process_message("Hello, how are you?"):
        response += chunk
    
    assert "hello" in response.lower() or "hi" in response.lower()
```

### 3. UI Tests

```python
# tests/test_ui.py
from PyQt6.QtTest import QTest
from src.ui.main_window import MainWindow

def test_api_key_input(qtbot):
    window = MainWindow(None)
    qtbot.addWidget(window)
    
    # Simulate typing API key
    window.settings.api_key_input.setText("test_key_123")
    assert window.settings.api_key_input.text() == "test_key_123"
```

---

## Monitoring & Logging

### 1. Structured Logging

```python
# src/utils/logging_config.py
from loguru import logger
import sys

def setup_logging(level: str = "INFO"):
    logger.remove()  # Remove default handler
    
    # Console logging
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level
    )
    
    # File logging
    logger.add(
        "logs/app_{time}.log",
        rotation="500 MB",
        retention="10 days",
        level="DEBUG"
    )
    
    # Error logging
    logger.add(
        "logs/errors_{time}.log",
        level="ERROR",
        rotation="100 MB"
    )
```

### 2. Performance Metrics

```python
# src/utils/metrics.py
import time
from functools import wraps

def track_time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} took {duration:.2f}s")
        return result
    return wrapper

# Usage
@track_time
async def process_message(message: str):
    # ... processing ...
    pass
```

---

## Roadmap & Future Enhancements

### Phase 4: Advanced Features (Months 3-4)

1. **Multi-Agent Collaboration**
   - Multiple specialized agents working together
   - Agent-to-agent communication
   - Task delegation

2. **Plugin System**
   - Third-party plugin support
   - Custom tool integration
   - Community marketplace

3. **Advanced Memory**
   - Knowledge graph representation
   - Automatic knowledge extraction
   - Memory consolidation

4. **Computer Vision**
   - Screen understanding
   - Visual grounding
   - Image generation

### Phase 5: Enterprise Features (Months 5-6)

1. **Team Collaboration**
   - Shared workspaces
   - Agent sharing
   - Role-based access

2. **API & Integrations**
   - REST API for external apps
   - Slack/Discord bots
   - Zapier integration

3. **Analytics Dashboard**
   - Usage statistics
   - Performance metrics
   - Cost tracking

---

## Contributing Guidelines

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings
- Keep functions small

### Git Workflow
```bash
# Create feature branch
git checkout -b feature/amazing-feature

# Make changes
git add .
git commit -m "Add amazing feature"

# Push and create PR
git push origin feature/amazing-feature
```

### Pull Request Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Screenshots
(if applicable)
```

---

## License & Legal

### Recommended License
MIT License - permissive, allows commercial use

### Privacy Policy Requirements
- Data collection disclosure
- User rights explanation
- Third-party service usage
- Data retention policy

### Terms of Service
- Acceptable use policy
- Limitation of liability
- Warranty disclaimer
- Dispute resolution

---

## Support & Community

### Documentation
- User guide
- API documentation
- Video tutorials
- FAQ

### Community Channels
- GitHub Discussions
- Discord server
- Twitter/X updates
- Blog for announcements

### Support Tiers
1. **Community**: GitHub issues, discussions
2. **Pro**: Email support, priority bugs
3. **Enterprise**: Dedicated support, SLA

---

## Conclusion

This blueprint provides a comprehensive foundation for building a production-ready AI agent with NVIDIA's models. Key success factors:

1. **Modular Architecture**: Easy to extend and maintain
2. **Security First**: Protect user data and privacy
3. **User Experience**: Intuitive, responsive interface
4. **Reliable Performance**: Robust error handling and testing
5. **Active Development**: Regular updates and community engagement

### Next Steps

1. Set up development environment
2. Obtain NVIDIA API key
3. Follow Phase 1 implementation
4. Join community for support
5. Iterate based on user feedback

**Good luck building your AI agent!** 🚀

---

## Appendix

### A. NVIDIA NIM API Models

Available models as of Feb 2025:
- `nvidia/kimi-k-2.5`: Latest, best performance
- `nvidia/kimi-k-2`: Previous version, faster
- `nvidia/llama-3.1-405b-instruct`: Large, powerful
- `nvidia/llama-3.1-70b-instruct`: Balanced
- `nvidia/llama-3.1-8b-instruct`: Fast, lightweight

### B. Recommended Hardware

**Minimum**:
- CPU: 4 cores, 2.5 GHz
- RAM: 8 GB
- Storage: 10 GB SSD
- GPU: Not required (CPU inference)

**Recommended**:
- CPU: 8 cores, 3.5 GHz
- RAM: 16 GB
- Storage: 50 GB SSD
- GPU: NVIDIA GPU with 8GB VRAM (for local models)

### C. Environment Variables

```bash
# .env file
NVIDIA_API_KEY=your_api_key_here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
DEFAULT_MODEL=nvidia/kimi-k-2.5
LOG_LEVEL=INFO
DB_PATH=./data/agent.db
CHROMA_PATH=./data/chroma
```

### D. Useful Resources

- [NVIDIA NIM Documentation](https://docs.nvidia.com/nim/)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [Playwright Documentation](https://playwright.dev/python/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)

---

**Document Version**: 1.0.0  
**Last Updated**: February 16, 2026  
**Author**: AI Agent Development Team  
**Contact**: support@nvidia-ai-agent.dev
