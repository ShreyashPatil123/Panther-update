# NVIDIA AI Agent

A production-ready, native Python desktop application that leverages NVIDIA's AI models to provide an intelligent assistant with speech-to-speech interaction, browser automation, file system access, and persistent memory.

## Features

- **Speech-to-Speech Interaction**: Voice activity detection, STT with faster-whisper, TTS with piper
- **Browser Automation**: Control browsers with Playwright for web tasks
- **File System Access**: Permission-based file operations with monitoring
- **Persistent Memory**: SQLite + ChromaDB for semantic search and long-term memory
- **Professional UI**: Native PyQt6 interface with dark theme
- **NVIDIA NIM Integration**: Support for Kimi and Llama models

## Getting Started

### Prerequisites

- Python 3.11+
- NVIDIA API key from [NVIDIA NIM](https://nvidia.com/nim)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/nvidia-ai-agent.git
cd nvidia-ai-agent
```

2. Install dependencies:
```bash
pip install poetry
poetry install
```

3. Set up your environment variables:
```bash
cp .env.example .env
```
Then open `.env` and replace `your_api_key_here` with your actual NVIDIA API key:
```
NVIDIA_API_KEY=nvapi-your-actual-key-here
```

4. Run the application:
```bash
poetry run python main.py
```

> **Note:** The `.env` file is gitignored and will never be committed. Each developer must create their own `.env` from `.env.example`.

### Alternative: Configure via Settings UI

Instead of editing `.env`, you can also set your API key through the app:
1. Launch the application
2. Click "Settings" in the sidebar
3. Enter your NVIDIA API key
4. Test the connection
5. Start chatting!

## Architecture

```
nvidia-ai-agent/
├── src/
│   ├── api/           # NVIDIA NIM API client
│   ├── core/          # Agent orchestrator
│   ├── capabilities/  # Browser, files, speech, research
│   ├── memory/        # Memory system (SQLite + ChromaDB)
│   ├── ui/            # PyQt6 interface
│   ├── utils/         # Utilities
│   └── config/        # Configuration
├── tests/             # Test suite
├── data/              # Data storage
├── logs/              # Application logs
└── main.py            # Entry point
```

## Development

### Phase 1: Foundation (Complete)
- Project structure
- NVIDIA API client with streaming
- Memory system with semantic search
- Agent orchestrator
- Basic Qt6 UI with chat interface

### Phase 2: Advanced Features (Planned)
- Browser controller (Playwright)
- File system manager
- Speech interface (STT/TTS)
- Research engine

### Phase 3: Production Ready (Planned)
- Security hardening
- UI/UX polish
- Packaging and distribution

## Security

- API keys stored in OS keyring
- Local memory storage with optional encryption
- Permission-based file access
- Browser isolation

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

- GitHub Issues: [Report bugs](https://github.com/yourusername/nvidia-ai-agent/issues)
- Documentation: [Wiki](https://github.com/yourusername/nvidia-ai-agent/wiki)

## Acknowledgments

- NVIDIA for NIM API
- Anthropic for Claude Cowork inspiration
- Open source community
