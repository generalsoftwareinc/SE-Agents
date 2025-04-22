from typing import List

from dotenv import load_dotenv
from duckduckgo_search import DDGS
from exa_py import Exa
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


class ExaSearchBase(Tool):
    def __init__(self, api_key: str):
        super().__init__(
            name="web_search",
            description="Search the web using Exa AI - performs real-time web searches and can scrape content from specific URLs. Supports configurable result counts and returns the content from the most relevant websites.",
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True,
                },
                "num_results": {
                    "type": "int",
                    "description": "Number of results to return.",
                    "required": False,
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
                "start_published_date": {
                    "type": "string",
                    "description": "Start publication date in ISO format (like 2025-04-08T04:00:00.000Z). Results will only include links with a published date after this date.",
                    "required": False,
                },
                "end_published_date": {
                    "type": "string",
                    "description": "End publication date in ISO format (like 2025-04-08T04:00:00.000Z). Results will only include links with a published date before this date.",
                    "required": False,
                },
            },
        )

        self.client = Exa(api_key=api_key)

    def _process_parameters(self, **kwargs):
        """
        Extract and process Exa search parameters from kwargs.

        Returns:
            tuple: (query, num_results, include_domains, exclude_domains, start_published_date, end_published_date)

        Raises:
            ValueError: If a required parameter is missing or invalid.
        """
        query = kwargs.get("query")
        if not query:
            raise ValueError("Missing required parameter 'query'")
        num_results = kwargs.get("num_results")
        include_domains = kwargs.get("include_domains")
        exclude_domains = kwargs.get("exclude_domains")
        start_published_date = kwargs.get("start_published_date")
        end_published_date = kwargs.get("end_published_date")

        if include_domains is not None:
            include_domains = self._convert_to_list(include_domains)
        if exclude_domains is not None:
            exclude_domains = self._convert_to_list(exclude_domains)

        return (
            query,
            num_results,
            include_domains,
            exclude_domains,
            start_published_date,
            end_published_date,
        )

    def _convert_to_list(self, value) -> List[str]:
        """
        Convert input to a list of strings.

        Accepts either a comma-separated string or a list of strings.
        Strips whitespace from each element.
        Raises ValueError if the input is neither a string nor a list of strings.

        Args:
            value (str or list of str): Input to convert.

        Returns:
            List[str]: List of strings.

        Raises:
            ValueError: If input is not a string or a list of strings.
        """
        if isinstance(value, str):
            return [d.strip() for d in value.split(",")]
        elif isinstance(value, list) and all(isinstance(d, str) for d in value):
            return value
        else:
            raise ValueError(
                "Value must be a list of strings or a comma-separated string."
            )


class ExaSearch(ExaSearchBase):
    def execute(self, **kwargs) -> str:
        (
            query,
            num_results,
            include_domains,
            exclude_domains,
            start_published_date,
            end_published_date,
        ) = self._process_parameters(**kwargs)

        results = []
        separator = "\n==============================================================================\n"
        for r in self.client.search(
            query=query,
            num_results=num_results if num_results is not None else 10,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        ).results:
            results.append(f"- {r.title}\n  URL: {r.url}")
        return f"Search results:{separator}" + separator.join(results)


class ExaCrawl(Tool):
    def __init__(self, api_key: str):
        super().__init__(
            name="crawl",
            description="Extract content from specific URLs using Exa AI - performs targeted crawling of web pages to retrieve their full content. Useful for reading articles, PDFs, or any web page when you have the exact URL. Returns the complete text content of the specified URL.",
            parameters={
                "url": {
                    "type": "string",
                    "description": "URL of the page to fetch",
                    "required": True,
                }
            },
        )
        self.client = Exa(api_key=api_key)

    def execute(self, **kwargs) -> str:
        url = kwargs.get("url")
        if not url:
            return "Error: No URL provided"

        try:
            # Use the Exa client to fetch the page
            response = self.client.get_contents(
                urls=[url], text={"max_characters": 16000, "include_html_tags": False}
            )
            content = response.results[0].text

            return content
        except Exception as e:
            return f"Error fetching page: {e}"


class ExaSearchContent(ExaSearchBase):

    def execute(self, **kwargs) -> str:
        (
            query,
            num_results,
            include_domains,
            exclude_domains,
            start_published_date,
            end_published_date,
        ) = self._process_parameters(**kwargs)

        results = []
        separator = "\n==============================================================================\n"
        for r in self.client.search_and_contents(
            query=query,
            num_results=num_results if num_results is not None else 3,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        ).results:
            results.append(f"- {r.title}\n  URL: {r.url}\n  Body: {r.text}")
        return f"Search results:{separator}" + separator.join(results)
