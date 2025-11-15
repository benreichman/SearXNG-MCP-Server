#!/usr/bin/env python3
"""
SearXNG HTTP MCP Server for LM Studio
Provides web search and scraping capabilities using your local SearXNG instance
Implements proper MCP HTTP/SSE protocol for LM Studio compatibility
"""

import asyncio
import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Configuration
SEARXNG_BASE_URL = "http://localhost:8080/search"
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_WORDS = 5000
REQUEST_TIMEOUT = 20
SERVER_PORT = 8765

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("searxng-mcp")

# FastAPI app
app = FastAPI(title="SearXNG MCP Server", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MCP Protocol Models - Fixed to handle both string and numeric IDs
class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

class WebSearchTools:
    """Web search and scraping utilities"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
    
    def remove_emojis(self, text: str) -> str:
        """Remove emojis from text"""
        return "".join(c for c in text if not unicodedata.category(c).startswith("So"))
    
    def format_text(self, text: str) -> str:
        """Clean and format scraped text"""
        soup = BeautifulSoup(text, "html.parser")
        formatted_text = soup.get_text(separator=" ", strip=True)
        formatted_text = unicodedata.normalize("NFKC", formatted_text)
        formatted_text = re.sub(r"\s+", " ", formatted_text)
        formatted_text = formatted_text.strip()
        return self.remove_emojis(formatted_text)
    
    def truncate_to_words(self, text: str, word_limit: int) -> str:
        """Truncate text to specified word count"""
        words = text.split()
        if len(words) <= word_limit:
            return text
        return " ".join(words[:word_limit])
    
    async def search_web(self, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> List[Dict[str, Any]]:
        """Search SearXNG and scrape the resulting pages"""
        logger.info(f"Searching for: {query}")
        
        params = {
            "q": query,
            "format": "json",
            "engines": "duckduckgo,google,bing,brave"
        }
        
        try:
            response = requests.get(
                SEARXNG_BASE_URL,
                params=params,
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            search_data = response.json()
            
            results = search_data.get("results", [])
            limited_results = results[:max_results]
            
            logger.info(f"Found {len(limited_results)} search results")
            
            scraped_results = []
            for result in limited_results:
                scraped_result = await self.scrape_url(
                    result["url"],
                    title=result.get("title", ""),
                    snippet=result.get("content", "")
                )
                if scraped_result:
                    scraped_results.append(scraped_result)
            
            logger.info(f"Successfully scraped {len(scraped_results)} pages")
            return scraped_results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Search failed: {str(e)}")
            return [{"error": f"Search failed: {str(e)}"}]
    
    async def scrape_url(self, url: str, title: str = "", snippet: str = "") -> Optional[Dict[str, Any]]:
        """Scrape content from a specific URL"""
        try:
            response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            if not title and soup.title:
                title = soup.title.string.strip()
            
            content = self.format_text(soup.get_text(separator=" ", strip=True))
            truncated_content = self.truncate_to_words(content, DEFAULT_MAX_WORDS)
            
            return {
                "title": self.remove_emojis(title or "No title"),
                "url": url,
                "content": truncated_content,
                "snippet": self.remove_emojis(snippet or ""),
                "word_count": len(truncated_content.split())
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to scrape {url}: {str(e)}")
            return None
    
    async def get_website(self, url: str) -> Dict[str, Any]:
        """Scrape a specific website URL"""
        logger.info(f"Scraping website: {url}")
        
        result = await self.scrape_url(url)
        if result:
            return result
        else:
            return {
                "url": url,
                "error": "Failed to scrape website",
                "content": ""
            }

# Initialize tools
web_tools = WebSearchTools()

# MCP Protocol Implementation
async def handle_mcp_method(method: str, params: Optional[Dict[str, Any]], request_id: Optional[Union[str, int]]):
    """Handle MCP protocol methods"""
    
    # Handle notifications (no response needed)
    if method.startswith("notifications/"):
        logger.info(f"Received notification: {method}")
        return None  # Notifications don't get responses
    
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "searxng-search",
                "version": "1.0.0"
            }
        }
    
    elif method == "tools/list":
        return {
            "tools": [
                {
                    "name": "search_web",
                    "description": "Search the web using SearXNG and scrape the resulting pages. Use this for finding current information, news, facts, or any web content.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to find relevant web content"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of pages to scrape (default: 5)",
                                "default": DEFAULT_MAX_RESULTS
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "get_website",
                    "description": "Scrape content from a specific website URL. Use this when you have a specific URL you want to extract content from.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL of the website to scrape"
                            }
                        },
                        "required": ["url"]
                    }
                }
            ]
        }
    
    elif method == "tools/call":
        if not params:
            raise HTTPException(status_code=400, detail="Missing parameters for tool call")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "search_web":
            query = arguments.get("query", "")
            max_results = arguments.get("max_results", DEFAULT_MAX_RESULTS)
            
            if not query:
                raise HTTPException(status_code=400, detail="Search query is required")
            
            results = await web_tools.search_web(query, max_results)
            
            if results and not any("error" in result for result in results):
                formatted_results = []
                for i, result in enumerate(results, 1):
                    formatted_results.append(
                        f"**Result {i}: {result['title']}**\n"
                        f"URL: {result['url']}\n"
                        f"Content: {result['content'][:500]}{'...' if len(result['content']) > 500 else ''}\n"
                        f"Word Count: {result['word_count']}\n"
                    )
                
                response_text = (
                    f"Web search completed for query: '{query}'\n"
                    f"Found {len(results)} relevant pages:\n\n" + 
                    "\n---\n".join(formatted_results)
                )
            else:
                error_msg = results[0].get("error", "Unknown error") if results else "No results found"
                response_text = f"Search failed: {error_msg}"
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": response_text
                    }
                ]
            }
        
        elif tool_name == "get_website":
            url = arguments.get("url", "")
            
            if not url:
                raise HTTPException(status_code=400, detail="URL is required")
            
            result = await web_tools.get_website(url)
            
            if "error" not in result:
                response_text = (
                    f"**{result['title']}**\n"
                    f"URL: {result['url']}\n"
                    f"Content: {result['content']}\n"
                    f"Word Count: {result['word_count']}"
                )
            else:
                response_text = f"Failed to scrape website: {result['error']}"
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": response_text
                    }
                ]
            }
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown method: {method}")

# HTTP endpoints
@app.post("/")
async def handle_mcp_post(request: Request):
    """Handle MCP HTTP requests"""
    try:
        body = await request.json()
        
        # Handle both single requests and batch requests
        if isinstance(body, list):
            # Batch request
            responses = []
            for req in body:
                try:
                    result = await handle_mcp_method(
                        req.get("method"),
                        req.get("params"),
                        req.get("id")
                    )
                    # Only add response if it's not a notification (result is not None)
                    if result is not None:
                        responses.append({
                            "jsonrpc": "2.0",
                            "id": req.get("id"),
                            "result": result
                        })
                except Exception as e:
                    # Only add error response if it's not a notification
                    if not req.get("method", "").startswith("notifications/"):
                        responses.append({
                            "jsonrpc": "2.0",
                            "id": req.get("id"),
                            "error": {
                                "code": -32603,
                                "message": "Internal error",
                                "data": str(e)
                            }
                        })
            return responses
        else:
            # Single request
            result = await handle_mcp_method(
                body.get("method"),
                body.get("params"),
                body.get("id")
            )
            # Only return response if it's not a notification
            if result is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": result
                }
            else:
                # For notifications, return empty 200 response
                return JSONResponse(status_code=200, content={})
    
    except Exception as e:
        logger.error(f"Error handling MCP request: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }
        )

@app.get("/sse")
async def sse_endpoint():
    """SSE endpoint for MCP (return 405 to indicate not supported)"""
    raise HTTPException(status_code=405, detail="SSE not supported, use HTTP POST")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "searxng_url": SEARXNG_BASE_URL}

@app.get("/")
async def sse_fallback(request: Request):
    """Handle SSE requests that LM Studio tries as fallback"""
    # Check if this is an SSE request
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        # Return proper SSE response
        async def sse_generator():
            # Send initial connection event
            yield "data: {\"jsonrpc\":\"2.0\",\"method\":\"initialized\",\"params\":{}}\n\n"
            # Keep connection alive
            while True:
                await asyncio.sleep(1)
                yield "data: {\"type\":\"ping\"}\n\n"
        
        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
    else:
        # Regular GET request - return server info
        return {
            "name": "SearXNG MCP Server",
            "version": "1.0.0",
            "protocol": "MCP HTTP",
            "endpoints": {
                "mcp": "POST /",
                "health": "GET /health"
            }
        }

if __name__ == "__main__":
    logger.info("Starting SearXNG HTTP MCP Server...")
    logger.info(f"SearXNG URL: {SEARXNG_BASE_URL}")
    logger.info(f"Server will run on http://localhost:{SERVER_PORT}")
    
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")