# GitHub Tools & CLI Tools for Raspberry Pi AI Assistant

*Researched: 2026-02-13 | Focus: CLI-friendly, lightweight, ARM64-compatible*

---

## 1. 💰 Financial Tools

### OpenBB Platform
- **URL:** https://github.com/OpenBB-finance/OpenBBTerminal (~36k ⭐)
- **What:** Investment research platform with CLI and Python interfaces. Access stocks, options, crypto, forex, macro data from dozens of providers.
- **API keys:** Free tier available; premium data providers need keys (Yahoo Finance works free)
- **ARM64:** Python-based, runs on Pi with some heavy deps (pandas, scipy)
- **Language:** Python
- **Note:** Already partially overlaps with your existing yfinance/finviz setup, but much more comprehensive

### PyPortfolioOpt
- **URL:** https://github.com/PyPortfolio/PyPortfolioOpt (~4.5k ⭐)
- **What:** Portfolio optimization library — mean-variance, Black-Litterman, Hierarchical Risk Parity, efficient frontier. Great for optimizing your paper trading portfolio.
- **API keys:** Free (no external APIs needed, uses price data you provide)
- **ARM64:** ✅ Pure Python + numpy/scipy
- **Language:** Python

### Cointop
- **URL:** https://github.com/cointop-sh/cointop (~4.4k ⭐)
- **What:** Fast, lightweight interactive terminal UI for tracking cryptocurrency prices in real-time. Vim-style keybindings, htop-inspired.
- **API keys:** Free (CoinGecko API, no key needed)
- **ARM64:** ✅ Single Go binary, ARM64 builds available
- **Language:** Go
- **Note:** Archived but still functional

### Ticker
- **URL:** https://github.com/achannarasappa/ticker (~5k ⭐)
- **What:** Terminal stock watcher and position tracker. Live quotes in your terminal.
- **API keys:** Free (Yahoo Finance)
- **ARM64:** ✅ Go binary with ARM64 releases
- **Language:** Go

### Options Python Library (wallstreet)
- **URL:** https://github.com/mcdallas/wallstreet (~1.2k ⭐)
- **What:** Real-time stock and option data with Black-Scholes pricing and Greeks calculation.
- **API keys:** Free
- **ARM64:** ✅ Pure Python
- **Language:** Python

### ccxt
- **URL:** https://github.com/ccxt/ccxt (~33k ⭐)
- **What:** Unified crypto trading API supporting 100+ exchanges. Trade, fetch orderbooks, balances, OHLCV data.
- **API keys:** Exchange API keys needed for trading; public data is free
- **ARM64:** ✅ Python/JS/PHP
- **Language:** Python, JavaScript, PHP

### Riskfolio-Lib
- **URL:** https://github.com/dcajasn/Riskfolio-Lib (~3k ⭐)
- **What:** Quantitative portfolio optimization with risk models, CVaR, drawdown constraints. More advanced than PyPortfolioOpt.
- **API keys:** Free
- **ARM64:** ✅ Python + scipy
- **Language:** Python

---

## 2. 📋 Productivity

### Taskwarrior
- **URL:** https://github.com/GothenburgBitFactory/taskwarrior (~4.5k ⭐)
- **What:** Command-line task management with tags, projects, priorities, due dates, recurrence. The gold standard for CLI todos.
- **API keys:** Free
- **ARM64:** ✅ C++ with ARM builds in apt repos
- **Language:** C++ (CLI tool)

### nb
- **URL:** https://github.com/xwmx/nb (~6.5k ⭐)
- **What:** CLI and local web note-taking, bookmarking, archiving, and knowledge base with linking, tagging, search, Git versioning, and encryption.
- **API keys:** Free
- **ARM64:** ✅ Bash script
- **Language:** Bash

### Buku
- **URL:** https://github.com/jarun/buku (~6.5k ⭐)
- **What:** Powerful command-line bookmark manager with browser integration. SQLite-backed, supports tags, search, import/export.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python

### pass (password-store)
- **URL:** https://github.com/zx2c4/password-store (~7.5k ⭐)
- **What:** Simple password manager using GPG encryption and Git for version control. Unix philosophy — each password is a GPG-encrypted file.
- **API keys:** Free
- **ARM64:** ✅ Bash script + GPG
- **Language:** Bash

### gopass
- **URL:** https://github.com/gopasspw/gopass (~5.9k ⭐)
- **What:** Modern rewrite of pass with team sharing, multiple stores, browser integration. Compatible with pass.
- **API keys:** Free
- **ARM64:** ✅ Go binary
- **Language:** Go

### dstask
- **URL:** https://github.com/naggie/dstask (~800 ⭐)
- **What:** Git-powered terminal task manager with markdown notes per task. Single binary, syncs via Git.
- **API keys:** Free
- **ARM64:** ✅ Go binary
- **Language:** Go

---

## 3. 🕷️ Data/Scraping

### Newsboat
- **URL:** https://github.com/newsboat/newsboat (~3k ⭐)
- **What:** Terminal RSS/Atom feed reader (fork of Newsbeuter). Supports Miniflux, TTRSS, Inoreader backends. Scriptable with macros.
- **API keys:** Free
- **ARM64:** ✅ In apt repos
- **Language:** C++/Rust

### Miniflux
- **URL:** https://github.com/miniflux/v2 (~7k ⭐)
- **What:** Minimalist, opinionated RSS reader. Self-hosted, PostgreSQL-backed, REST API, extremely fast and lightweight.
- **API keys:** Free (self-hosted)
- **ARM64:** ✅ Go binary with ARM64 builds
- **Language:** Go

### Scrapy
- **URL:** https://github.com/scrapy/scrapy (~53k ⭐)
- **What:** Fast, high-level web scraping framework. Pipeline-based, supports CSS/XPath selectors, middleware, export to JSON/CSV/SQLite.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python

### httpie
- **URL:** https://github.com/httpie/cli (~34k ⭐)
- **What:** Human-friendly HTTP client for the command line. Great for quick API testing and data fetching.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python

### jq
- **URL:** https://github.com/jqlang/jq (~31k ⭐)
- **What:** Lightweight command-line JSON processor. Essential for parsing API responses and data pipelines.
- **API keys:** Free
- **ARM64:** ✅ Already installed on your Pi
- **Language:** C

### pup
- **URL:** https://github.com/ericchiang/pup (~8.1k ⭐)
- **What:** Command-line HTML parser — like jq but for HTML. CSS selectors on stdin.
- **API keys:** Free
- **ARM64:** ✅ Go binary
- **Language:** Go

### shot-scraper
- **URL:** https://github.com/simonw/shot-scraper (~1.6k ⭐)
- **What:** CLI tool for taking screenshots and scraping web pages with JavaScript support (Playwright-based).
- **API keys:** Free
- **ARM64:** ⚠️ Needs Chromium; works on Pi but heavy
- **Language:** Python

---

## 4. 📊 Monitoring

### btop
- **URL:** https://github.com/aristocratos/btop (~22k ⭐)
- **What:** Beautiful resource monitor showing CPU, memory, disk, network, and processes. TUI with mouse support.
- **API keys:** Free
- **ARM64:** ✅ In apt repos
- **Language:** C++

### Glances
- **URL:** https://github.com/nicolargo/glances (~27k ⭐)
- **What:** Cross-platform system monitoring with web UI, REST API, and export to InfluxDB/Prometheus. Perfect for headless monitoring.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python

### Uptime Kuma
- **URL:** https://github.com/louislam/uptime-kuma (~63k ⭐)
- **What:** Self-hosted website monitoring with 90+ notification services (Telegram, Slack, Discord, email). Beautiful status pages.
- **API keys:** Free (self-hosted)
- **ARM64:** ✅ Node.js, Docker ARM64 available
- **Language:** JavaScript/Node

### ntfy
- **URL:** https://github.com/binwiederhier/ntfy (~19k ⭐)
- **What:** Simple pub/sub notification service. Send push notifications from scripts with a single curl command.
- **API keys:** Free (self-hosted or free cloud tier)
- **ARM64:** ✅ Go binary with ARM64 builds
- **Language:** Go

### Gotify
- **URL:** https://github.com/gotify/server (~12k ⭐)
- **What:** Self-hosted push notification server with REST API and Android app. Simple, reliable, lightweight.
- **API keys:** Free (self-hosted)
- **ARM64:** ✅ Go binary
- **Language:** Go

### Healthchecks
- **URL:** https://github.com/healthchecks/healthchecks (~8.5k ⭐)
- **What:** Cron job monitoring — alerts you when your scheduled tasks don't run. Perfect for monitoring your market analysis crons.
- **API keys:** Free tier at healthchecks.io or self-host
- **ARM64:** ✅ Python/Django
- **Language:** Python

---

## 5. 💬 Communication

### Matterbridge
- **URL:** https://github.com/42wim/matterbridge (~6.8k ⭐)
- **What:** Bridges between IRC, Slack, Discord, Telegram, Matrix, WhatsApp, Teams, and 20+ other chat platforms. Single binary.
- **API keys:** Platform tokens needed (Slack bot token, etc.)
- **ARM64:** ✅ Go binary
- **Language:** Go

### Himalaya
- **URL:** https://github.com/pimalaya/himalaya (~3.2k ⭐)
- **What:** CLI email client supporting IMAP/SMTP. Already on your system! Scriptable, composable.
- **API keys:** Free
- **ARM64:** ✅ Rust binary (already installed)
- **Language:** Rust

### neomutt
- **URL:** https://github.com/neomutt/neomutt (~3.4k ⭐)
- **What:** Command-line email client — feature-rich TUI with scripting, filtering, PGP support.
- **API keys:** Free
- **ARM64:** ✅ In apt repos
- **Language:** C

### signal-cli
- **URL:** https://github.com/AsamK/signal-cli (~3.2k ⭐)
- **What:** CLI and D-Bus interface for Signal Messenger. Send/receive messages programmatically.
- **API keys:** Free (needs Signal phone number)
- **ARM64:** ✅ Java (needs JRE)
- **Language:** Java

---

## 6. 🤖 AI/ML

### Ollama
- **URL:** https://github.com/ollama/ollama (~120k+ ⭐)
- **What:** Run local LLMs easily — pull models like llama3, mistral, phi, gemma. OpenAI-compatible API. Dead simple CLI.
- **API keys:** Free
- **ARM64:** ✅ Native ARM64 builds, works on Pi 5 with 8GB
- **Language:** Go
- **Note:** Best small models for Pi: phi-3-mini, gemma-2b, tinyllama

### llama.cpp
- **URL:** https://github.com/ggml-org/llama.cpp (~75k+ ⭐)
- **What:** LLM inference in C/C++ with quantization. The engine behind Ollama. Maximum performance on limited hardware.
- **API keys:** Free
- **ARM64:** ✅ Optimized for ARM NEON
- **Language:** C/C++

### whisper.cpp
- **URL:** https://github.com/ggerganov/whisper.cpp (~37k ⭐)
- **What:** OpenAI Whisper speech-to-text in C/C++. Fast local transcription without Python overhead.
- **API keys:** Free
- **ARM64:** ✅ ARM NEON optimized
- **Language:** C/C++

### Piper TTS
- **URL:** https://github.com/rhasspy/piper (~7.5k ⭐)
- **What:** Fast local text-to-speech with natural voices. Runs entirely offline, many voice models available.
- **API keys:** Free
- **ARM64:** ✅ Native ARM64, designed for Raspberry Pi
- **Language:** C++ (Python bindings)

### ChromaDB
- **URL:** https://github.com/chroma-core/chroma (~25k ⭐)
- **What:** Embedded vector database for AI apps. Store embeddings, do similarity search. Simple Python API.
- **API keys:** Free
- **ARM64:** ✅ Python with SQLite backend
- **Language:** Python

### LightRAG
- **URL:** https://github.com/HKUDS/LightRAG (~14k ⭐)
- **What:** Simple and fast RAG framework with graph-based retrieval. Lightweight enough for edge devices.
- **API keys:** Needs LLM API key or use with Ollama locally
- **ARM64:** ✅ Python
- **Language:** Python

### sqlite-vec
- **URL:** https://github.com/asg017/sqlite-vec (~5k ⭐)
- **What:** SQLite extension for vector search. Zero-dependency vector database using your existing SQLite setup.
- **API keys:** Free
- **ARM64:** ✅ C, loadable SQLite extension
- **Language:** C
- **Note:** Perfect for your existing SQLite portfolio DB — add vector search without another database

---

## 7. 🏠 Home Automation

### Home Assistant CLI (hass-cli)
- **URL:** https://github.com/home-assistant-ecosystem/home-assistant-cli (~500 ⭐)
- **What:** Command-line interface for Home Assistant. Control devices, query states, trigger automations from terminal.
- **API keys:** Home Assistant API token
- **ARM64:** ✅ Python
- **Language:** Python

### Mosquitto
- **URL:** https://github.com/eclipse-mosquitto/mosquitto (~9.5k ⭐)
- **What:** Lightweight MQTT message broker — the backbone for IoT/home automation messaging.
- **API keys:** Free
- **ARM64:** ✅ In apt repos, designed for embedded systems
- **Language:** C

### ESPHome
- **URL:** https://github.com/esphome/esphome (~10.5k ⭐)
- **What:** System to control ESP8266/ESP32 devices via YAML config. OTA updates, MQTT, Home Assistant integration.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python/C++

### Zigbee2MQTT
- **URL:** https://github.com/Koenkk/zigbee2mqtt (~12.5k ⭐)
- **What:** Bridge Zigbee devices to MQTT without proprietary hubs. Supports 3000+ devices.
- **API keys:** Free (needs Zigbee USB adapter ~$20)
- **ARM64:** ✅ Node.js, popular on Raspberry Pi
- **Language:** JavaScript

---

## 8. 🎵 Media

### yt-dlp
- **URL:** https://github.com/yt-dlp/yt-dlp (~100k+ ⭐)
- **What:** Download audio/video from YouTube and 1000+ sites. Feature-packed fork of youtube-dl.
- **API keys:** Free
- **ARM64:** ✅ Python
- **Language:** Python

### ImageMagick
- **URL:** https://github.com/ImageMagick/ImageMagick (~12k ⭐)
- **What:** CLI image processing — resize, crop, convert, composite, effects. Already on your system.
- **API keys:** Free
- **ARM64:** ✅ In apt repos (already installed)
- **Language:** C

### mpv
- **URL:** https://github.com/mpv-player/mpv (~29k ⭐)
- **What:** Minimalist media player with CLI control. Scriptable, supports streaming, headless audio playback.
- **API keys:** Free
- **ARM64:** ✅ In apt repos
- **Language:** C

### cmus
- **URL:** https://github.com/cmus/cmus (~5.6k ⭐)
- **What:** Small, fast, ncurses-based music player for the terminal. Vim-style keybindings.
- **API keys:** Free
- **ARM64:** ✅ In apt repos
- **Language:** C

### Bark (suno-ai)
- **URL:** https://github.com/suno-ai/bark (~37k ⭐)
- **What:** Text-to-audio generation — speech, music, sound effects. More expressive than simple TTS.
- **API keys:** Free
- **ARM64:** ⚠️ Heavy for Pi (needs ~4GB RAM minimum), best with quantization
- **Language:** Python

---

## 🏆 Top Recommendations for BigClaw

### Highest-impact additions (you don't already have):

| Priority | Tool | Why |
|----------|------|-----|
| 🔴 High | **ntfy** | Push notifications from any script — one curl command |
| 🔴 High | **PyPortfolioOpt** | Optimize your paper trading portfolio allocations |
| 🔴 High | **sqlite-vec** | Add vector search to your existing SQLite DB |
| 🔴 High | **Ollama** | Run small LLMs locally for offline analysis |
| 🟡 Med | **Ticker** | Live stock quotes in terminal |
| 🟡 Med | **Glances** | Monitor your Pi with REST API export |
| 🟡 Med | **nb** | CLI note-taking with Git sync |
| 🟡 Med | **Miniflux** | Self-hosted RSS for news aggregation |
| 🟡 Med | **Healthchecks** | Monitor your cron jobs are running |
| 🟢 Low | **Piper TTS** | Local text-to-speech for voice alerts |
| 🟢 Low | **whisper.cpp** | Local speech-to-text |
| 🟢 Low | **Matterbridge** | Bridge Slack ↔ other platforms |

### Quick install commands:
```bash
# Monitoring & notifications
pip install glances
# ntfy: curl -sSL https://install.ntfy.sh | bash

# Financial
pip install pyportfolioopt
pip install ccxt

# Productivity
sudo apt install taskwarrior
# nb: curl -L https://raw.githubusercontent.com/xwmx/nb/master/nb -o /usr/local/bin/nb

# AI/ML
curl -fsSL https://ollama.ai/install.sh | sh
# Then: ollama pull phi3:mini

# Vector search for existing SQLite
pip install sqlite-vec
```

---

*Total tools cataloged: 42 across 8 categories*
*All verified to have ARM64 support or pure Python/Go/Rust portability*
