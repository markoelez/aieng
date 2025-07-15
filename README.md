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