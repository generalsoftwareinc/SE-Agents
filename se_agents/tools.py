from typing import List

from exa_py import Exa
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from firecrawl import FirecrawlApp


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
            name="web_search_tool",
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
    def __init__(self, api_key: str):
        super().__init__(
            name="fetch_page_tool",
            description="Fetch the contents of a specific page using Firecrawl",
            parameters={
                "url": {
                    "type": "string",
                    "description": "URL of the page to fetch",
                    "required": True,
                }
            },
        )
        self.client = FirecrawlApp(api_key=api_key)

    def execute(self, **kwargs) -> str:
        url = kwargs.get("url")
        if not url:
            return "Error: No URL provided"

        try:
            # Use the Firecrawl client to fetch the page
            response = self.client.scrape_url(url=url, params={"formats": ["markdown"]})
            markdown_content = response["markdown"]

            # Count words in the markdown content
            words = markdown_content.split()
            word_count = len(words)

            if word_count > 32000:
                # Extract first 16k words and last 16k words
                first_16k = " ".join(words[:16000])
                last_16k = " ".join(words[-16000:])
                return f"{first_16k}\n.......\n{last_16k}"
            else:
                return markdown_content
        except Exception as e:
            return f"Error fetching page: {e}"


class ExaSearchContent(Tool):
    def __init__(self, api_key: str):
        super().__init__(
            name="exa_web_search",
            description="Search the web using Exa Search",
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True,
                },
                "include_domains": {
                    "type": "List[string]",
                    "description": "List of comma-separated domains to include in the search.",
                    "required": False,
                },
                "exclude_domains": {
                    "type": "List[string]",
                    "description": "List of comma-separated domains to exclude from the search.",
                    "required": False,
                },
            },
        )

        self.client = Exa(api_key=api_key)

    def _convert_to_list(self, value) -> List[str]:
        """
        Converts a comma-separated string or a list of strings to a list of strings.
        """
        if isinstance(value, str):
            return [d.strip() for d in value.split(",")]
        elif isinstance(value, list) and all(isinstance(d, str) for d in value):
            return value
        else:
            raise ValueError("Value must be a list of strings or a comma-separated string.")

    def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        include_domains = kwargs.get("include_domains")
        exclude_domains = kwargs.get("exclude_domains")

        try:
            include_domains = self._convert_to_list(include_domains) if include_domains else None
            exclude_domains = self._convert_to_list(exclude_domains) if exclude_domains else None
        except ValueError as e:
            return f"Error: {str(e)}"

        print(include_domains, exclude_domains)

        if not query:
            return "Error: No query provided"

        results = []
        separator = "\n==============================================================================\n"
        for r in self.client.search_and_contents(query=query, num_results=3, include_domains=include_domains, exclude_domains=exclude_domains).results:
            results.append(f"- {r.title}\n  URL: {r.url}\n  Body: {r.text}")
            # print(f"=== Exa Consulted {r.url} ===")
            # time.sleep(3)
        return f"Search results:{separator}" + separator.join(results)
