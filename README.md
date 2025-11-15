# SearXNG MCP Server

A Model Context Protocol (MCP) server that provides web search and scraping capabilities using a local SearXNG instance. Designed for integration with LM Studio and other MCP-compatible AI clients.

## Features

- **Web Search**: Search across multiple engines (DuckDuckGo, Google, Bing, Brave) via SearXNG
- **Content Scraping**: Automatically scrape and format content from search results
- **Direct URL Scraping**: Extract content from specific URLs
- **Tor Support**: Optional anonymous scraping through Tor network
- **MCP Protocol**: Full implementation of MCP HTTP protocol for seamless AI assistant integration
- **Clean Text Extraction**: Remove emojis, normalize formatting, and limit word count

## Prerequisites

- Python 3.8+
- A running SearXNG instance (default: `http://localhost:8080`)

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure SearXNG is running locally at `http://localhost:8080`

## Configuration

Edit `searxng_mcp_server.py` to customize:

```python
SEARXNG_BASE_URL = "http://localhost:8080/search"  # Your SearXNG instance
DEFAULT_MAX_RESULTS = 5                            # Default search results
DEFAULT_MAX_WORDS = 5000                           # Max words per page
REQUEST_TIMEOUT = 20                               # Request timeout (seconds)
SERVER_PORT = 8765                                 # Server port
USE_TOR = False                                    # Route scraping through Tor (requires Tor on 127.0.0.1:9050)
```

### Tor Support

To enable anonymous scraping through Tor:

1. Install and start Tor service (must be running on `127.0.0.1:9050`)
2. Set `USE_TOR = True` in the configuration
3. Restart the server

When enabled, all web scraping requests will be routed through the Tor network.

## Usage

### Start the Server

```bash
python searxng_mcp_server.py
```

The server will run on `http://localhost:8765`

### Configure with LM Studio

Add to your LM Studio MCP settings:

```json
{
  "mcpServers": {
    "searxng": {
      "url": "http://localhost:8765",
      "transport": "http"
    }
  }
}
```

## Available Tools

### 1. search_web

Search the web and scrape resulting pages.

**Parameters:**
- `query` (required): Search query string
- `max_results` (optional): Number of results to scrape (default: 5)

**Example:**
```
Search for "latest AI developments" and show me the top 3 results
```

### 2. get_website

Scrape content from a specific URL.

**Parameters:**
- `url` (required): The URL to scrape

**Example:**
```
Get the content from https://example.com
```

## API Endpoints

- `POST /` - MCP protocol endpoint
- `GET /health` - Health check endpoint
- `GET /` - Server info (or SSE fallback)

## How It Works

1. Receives MCP tool calls from AI assistants
2. Queries SearXNG with specified search terms
3. Retrieves search results in JSON format
4. Scrapes content from each result URL
5. Cleans and formats text (removes HTML, emojis, normalizes spacing)
6. Truncates content to word limit
7. Returns formatted results to the AI assistant

## License

MIT
