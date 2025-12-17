# AIENG

A terminal-based, model-agnostic AI coding assistant, inspired by GPT Codex

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Install uv

If you don't have uv installed, get it from [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

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
   OPENAI_API_KEY=your_api_key_here
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
   model = "gpt-5.1-codex"  # Default GPT Codex model
   api_base_url = "https://api.openai.com/v1"  # OpenAI GPT Codex endpoint
   
   # Examples for different providers:
   # Anthropic: api_base_url = "https://api.anthropic.com/v1"
   # Local: api_base_url = "http://localhost:11434/v1"
   ```

3. **Update API key** in `.env`:
   ```bash
   OPENAI_API_KEY=your_provider_api_key_here
   ```

## TODOs

- Improve agent narration between tasks
- Reduce redundant actions

## Development Workflow

1. **Install dev dependencies**
   ```bash
   uv sync --dev
   ```
2. **Install git hooks (Ruff formatting + Ty type checking)**
   ```bash
   uv run pre-commit install
   ```
3. **Run checks locally**
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run ty check
   ```

Every push and pull request is validated by the `CI` GitHub Actions workflow, which runs the same Ruff and Ty steps to keep formatting, linting, and type checking consistent.