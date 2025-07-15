# AIENG

A terminal-based, model-agnostic AI coding assistant, inspired by Claude Code

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Install uv

If you don't have uv installed, get it from [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/):

### Build from Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/markoelez/aieng.git
   cd aieng
   ```

2. **Install dependencies and build:**
   ```bash
   uv sync
   ```

3. **Install in development mode:**
   ```bash
   uv pip install -e .
   ```

4. **Set up environment variables:**
   
   Create a `.env` file in the project root:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your API key:
   ```
   API_KEY=your_api_key_here
   ```

5. **Run AIENG:**
   ```bash
   aieng
   ```

## Configuration

### Switching Models

AIENG is model agnostic. To switch models:

1. **Initialize configuration file** (if not already created):
   ```bash
   aieng
   # Type /init to create aieng.toml
   ```

2. **Edit `aieng.toml`** in your project directory:
   ```toml
   # Model Configuration
   model = "grok-4"  # Change to your desired model
   api_base_url = "https://api.x.ai/v1"  # Change to your provider's API endpoint
   
   # Examples for different providers:
   # OpenAI: api_base_url = "https://api.openai.com/v1"
   # Anthropic: api_base_url = "https://api.anthropic.com/v1"
   # Local: api_base_url = "http://localhost:11434/v1"
   ```

3. **Update API key** in `.env`:
   ```bash
   API_KEY=your_provider_api_key_here
   ```