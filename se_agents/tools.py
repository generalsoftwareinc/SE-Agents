import base64
import time
from abc import abstractmethod
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from duckduckgo_search import DDGS
from exa_py import Exa
from firecrawl import FirecrawlApp
from openai import Client
from requests import HTTPError


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        stream: bool = False,
        param_stream: str = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.stream = stream

        if stream and not param_stream:
            raise ValueError("Streaming tools must have a param_stream specified")
        self.param_stream = param_stream

    def _process_parameters(self, **kwargs: dict) -> dict:
        # Enforce required parameters
        for name, config in self.parameters.items():
            if config.get("required", False) and name not in kwargs:
                raise ValueError(f"Missing required parameter: {name}")

        processed_parameters = {}
        for param, value in kwargs.items():
            tool_param = self.parameters.get(param)
            if not tool_param:
                raise KeyError(f"{param} is not a parameter of the tool {self.name}")

            param_type = tool_param.get("type")
            if param_type == "int":
                processed_parameters[param] = int(value)
            elif param_type == "List[string]":
                processed_parameters[param] = self._convert_to_list(value)
            elif param_type == "bool":
                if not isinstance(value, str):
                    raise ValueError(
                        f"Expected a string for boolean parameter '{param}', but got {type(value).__name__}"
                    )
                boolean_str = value.strip().lower()
                if boolean_str not in ("true", "false"):
                    raise ValueError(f"{boolean_str} cannot be parsed into boolean")
                processed_parameters[param] = boolean_str == "true"
            else:
                processed_parameters[param] = value

        return processed_parameters

    def _convert_to_list(self, value) -> List[str] | None:
        """
        Convert input to a list of strings.

        Accepts either a comma-separated string or a list of strings.
        Strips whitespace from each element.
        Raises ValueError if the input is neither a string nor a list of strings.

        Args:
            value (str or list of str): Input to convert.

        Returns:
            List[str] | None: List of strings, or None if input is an empty string or empty list.

        Raises:
            ValueError: If input is not a string or a list of strings.
        """
        if value == "" or (isinstance(value, list) and len(value) == 0):
            return None
        if isinstance(value, str):
            return [d.strip() for d in value.split(",")]
        elif isinstance(value, list) and all(isinstance(d, str) for d in value):
            return value
        else:
            raise ValueError(
                "Value must be a list of strings or a comma-separated string."
            )

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
        params = self._process_parameters(**kwargs)
        query = params.get("query")
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
        params = self._process_parameters(**kwargs)
        url = params.get("url")
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


class ExaSearch(Tool):
    def __init__(self, api_key: str):
        super().__init__(
            name="web_search_tool",
            description="Search the web using Exa AI - performs real-time web searches and can scrape content from specific URLs. Supports configurable result counts and returns the content from the most relevant websites.",
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

    def execute(self, **kwargs) -> str:
        params = self._process_parameters(**kwargs)
        query = params.get("query")
        include_domains = params.get("include_domains")
        start_published_date = params.get("start_published_date") or None
        end_published_date = params.get("end_published_date") or None

        results = []
        separator = "\n==============================================================================\n"

        search_results = None

        while True:
            try:
                search_results = self.client.search_and_contents(
                    query,
                    include_domains=include_domains,
                    start_published_date=start_published_date,
                    end_published_date=end_published_date,
                    summary=True,
                ).results
                break
            except ValueError as e:
                msg = ""
                if e.args:
                    msg = str(e.args[0])

                status_code = getattr(e, "response", None) and getattr(
                    e.response, "status_code", None
                )

                if status_code == 429 or "429" in msg:
                    print("Rate limit exceeded (429). Retrying after 1 second...")
                    time.sleep(1)
                    continue
                else:
                    text = getattr(e, "response", None) and getattr(
                        e.response, "text", str(e)
                    )
                    raise Exception(
                        f"Error during search: {status_code or 'N/A'} - {text}"
                    )
            except Exception as e:
                raise Exception(f"An unexpected error occurred during search: {e}")

        if search_results is not None:
            try:
                for r in search_results:
                    results.append(
                        f"- {r.title}\n  URL: {r.url}\n  Summary: {r.summary}"
                    )
                return f"Search results:{separator}" + separator.join(results)
            except Exception as e:
                raise Exception(f"Error processing search results: {e}")
        else:
            return "Error: Search failed to return results after handling exceptions."


class ExaCrawl(Tool):
    def __init__(self, api_key: str):
        super().__init__(
            name="crawl_tool",
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
        params = self._process_parameters(**kwargs)
        url = params.get("url")
        if not url:
            return "Error: No URL provided"

        content = None
        retries = 0
        while True:
            try:
                livecrawl = "always" if retries == 0 else "never"
                response = self.client.get_contents(
                    urls=[url],
                    text={"max_characters": 64000, "include_html_tags": False},
                    livecrawl=livecrawl,
                )
                if response.results:
                    content = response.results[0].text
                break  # Exit loop if successful
            except ValueError as e:
                msg = ""
                if e.args:
                    msg = str(e.args[0])
                status_code = getattr(e, "response", None) and getattr(
                    e.response, "status_code", None
                )
                if status_code == 429 or "429" in msg:
                    print(
                        "Rate limit exceeded (429) for crawl. Retrying after 1 second..."
                    )
                    time.sleep(1)
                    continue
                else:
                    text = getattr(e, "response", None) and getattr(
                        e.response, "text", str(e)
                    )
                    if retries == 0 and not status_code:
                        retries += 1
                        print(
                            "==== Response returned N/A, retrying without livecrawl..."
                        )
                        continue

                    return f"Error fetching page: {status_code or 'N/A'} - {text}"  # Return error for non-429
            except Exception as e:
                return f"Error fetching page: {e}"  # Return error for other exceptions

        if content is not None:
            return content
        else:
            return "Error: Failed to fetch page content after handling exceptions."


class MockNumberTool(Tool):
    def __init__(self):
        super().__init__(
            name="mock_number_tool",
            description="A mock tool requiring a number (int or float) parameter.",
            parameters={
                "value": {  # Renamed parameter for clarity
                    "type": "number",
                    "description": "A number value (integer or float).",
                    "required": True,
                }
            },
        )

    def execute(self, **kwargs) -> str:
        params = self._process_parameters(**kwargs)
        value = params.get("value")
        if value is None:
            return "Error: Missing required parameter 'value'"
        try:
            num_value = float(value)
            return f"MockNumberTool executed successfully with value: {num_value}"
        except ValueError:
            return f"Error: Parameter 'value' must be a number, received: {value}"


class MockIntTool(Tool):
    def __init__(self):
        super().__init__(
            name="mock_int_tool",
            description="A mock tool requiring an integer parameter for testing.",
            parameters={
                "value": {
                    "type": "int",
                    "description": "An integer value.",
                    "required": True,
                }
            },
        )

    def execute(self, **kwargs) -> str:
        params = self._process_parameters(**kwargs)
        value = params.get("value")
        if value is None:
            return "Error: Missing required parameter 'value'"
        try:
            int_value = int(value)
            return f"MockIntTool executed successfully with value: {int_value}"
        except ValueError:
            return f"Error: Parameter 'value' must be an integer, received: {value}"


class ThinkTool(Tool):
    def __init__(self):
        super().__init__(
            name="think_tool",
            description="Use the tool to think about something. It will not obtain new information or change the database, but just append the thought to the log. Use it when complex reasoning or some cache memory is needed.",
            parameters={
                "thought": {
                    "type": "string",
                    "description": "A thought to think about.",
                    "required": True,
                }
            },
            stream=True,
            param_stream="thought",
        )

    def execute(self, **kwargs) -> str:
        params = self._process_parameters(**kwargs)
        thought = params.get("thought", "")
        return f"Thought logged: {thought}"


class VisionBaseTool(Tool):
    _accepted_formats = ["png", "jpg", "jpeg", "webp"]

    def __init__(self, name=None, description=None, parameters=None):
        name = "vision_tool" if not name else name

        super().__init__(
            name=name,
            description="Use the tool to interpret images uploaded by the user and perform classification and object detection tasks",
            parameters={
                "url": {
                    "type": "string",
                    "description": "A valid url that leads to an image",
                    "required": False,
                },
                "image": {
                    "type": "Image",
                    "description": "A valid image file",
                    "required": False,
                },
                "prompt": {
                    "type": "string",
                    "description": "What the user expects the model to detect/classify in the image",
                    "required": True,
                },
            },
        )

    @property
    @abstractmethod
    def ACCEPTED_FORMATS(self) -> List[str]:
        return self._accepted_formats

    def _process_parameters(self, **kwargs):

        params = super()._process_parameters(**kwargs)
        url: str = params.get("url")
        image_param = params.get("image")

        if not url and not image_param:
            raise KeyError(
                f"The '{self.name}' tool requires the 'url' or 'image' parameters."
            )

        return params


class OpenAIVisionTool(VisionBaseTool):
    def __init__(self):
        super().__init__("openai_vision_tool")
        self._accepted_formats = [".png", ".jpg", ".jpeg", ".webp", ".gif"]

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _process_parameters(self, **kwargs):
        params = super()._process_parameters(**kwargs)
        url = params.get("url")
        prompt = params.get("prompt")
        image_param = params.get("image")

        if url:
            return {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        image_path = Path(image_param)
        if image_path.exists() and image_path.suffix in self._accepted_formats:
            base64_image = self.encode_image(image_path)
            return {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }

        raise ValueError("The image format is not supported")

    async def execute(self, client: Client, model: str, **kwargs):

        image_msg = self._process_parameters(**kwargs)

        response = await client.chat.completions.create(
            # model="gpt-4.1-mini",
            model=model,
            messages=[image_msg],
            stream=False,
        )

        print(f"===OpenAI returned a response with type {type(response)}")

        return response.choices[0].message.content


class FinalOutput(Tool):
    def __init__(self):
        super().__init__(
            name="final_output_tool",
            description="Use this tool **only** to conclude **your current response cycle**, **after** all other necessary actions (like thinking or using other tools) for **this step** are complete. Provide your complete final response or summary of work done for **this step** in the 'result' parameter. This is required even for simple conversational replies where no other tools were needed.",
            parameters={
                "result": {
                    "type": "string",
                    "description": "The final result of the task",
                    "required": True,
                }
            },
            stream=True,
            param_stream="result",
        )

    def execute(self, **kwargs) -> str:
        params = self._process_parameters(**kwargs)
        return params["result"]
