import os
from typing import Dict, List

import requests
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()


class Tool:
    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def validate_parameters(self, params: dict) -> List[str]:
        errors = []
        for param_name, config in self.parameters.items():
            if config.get("required", False) and (
                param_name not in params or not params[param_name]
            ):
                errors.append(f"Missing required parameter: {param_name}")
            elif param_name in params:
                param_type = config.get("type", "string")
                try:
                    # For basic type checking
                    if param_type == "string" and not isinstance(
                        params[param_name], str
                    ):
                        errors.append(f"{param_name} must be a string")
                    elif param_type == "int" and not (
                        isinstance(params[param_name], int)
                        or params[param_name].isdigit()
                    ):
                        errors.append(f"{param_name} must be an integer")
                    elif param_type == "bool" and not (
                        isinstance(params[param_name], bool)
                        or params[param_name].lower() in ("true", "false")
                    ):
                        errors.append(f"{param_name} must be a boolean")
                except Exception as e:
                    errors.append(f"Error validating {param_name}: {str(e)}")
        return errors

    def execute(self, **kwargs) -> str:
        raise NotImplementedError()


class DuckDuckGoSearch(Tool):
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Search the web using DuckDuckGo",
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True,
                }
            },
        )

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: No query provided"

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                results.append(
                    f"- {r.get('title')}\n  URL: {r.get('href')}\n  {r.get('body')}"
                )
        return "Search results:\n" + "\n\n".join(results)


class FireCrawlFetchPage(Tool):
    def __init__(self):
        super().__init__(
            name="fetch_page",
            description="Fetch the contents of a specific page using Firecrawl",
            parameters={
                "url": {
                    "type": "string",
                    "description": "URL of the page to fetch",
                    "required": True,
                }
            },
        )

    def execute(self, **kwargs) -> str:
        url = kwargs.get("url")
        if not url:
            return "Error: No URL provided"

        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            return "Error: Firecrawl API key not found in environment variables"

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = requests.get(
                "https://api.firecrawl.dev/scrape",
                headers=headers,
                params={"url": url},
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return response.text
        except requests.exceptions.RequestException as e:
            return f"Error fetching page: {e}"
