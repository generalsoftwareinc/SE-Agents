import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from openai import Client
from duckduckgo_search import DDGS
from system_prompt import system_prompt


class Agent:
    def __init__(self, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.client = Client(api_key=api_key, base_url=base_url)
        self.model = model
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

    def _parse_tool_call(self, message: str) -> Optional[Dict[str, Dict[str, str]]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Handles tool calls both directly in the message and inside code blocks.
        """
        # Look for tool calls inside code blocks first
        code_block_match = re.search(r'```(?:xml|tool_code)?\s*\n?(.*?)\n?```', message, re.DOTALL)
        if code_block_match:
            message = code_block_match.group(1)
        
        tool_match = re.search(r"<([^>]+)>\n(.*?)\n</\1>", message, re.DOTALL)
        if not tool_match:
            return None

        tool_name = tool_match.group(1)
        tool_content = tool_match.group(2)

        # Parse parameters
        params = {}
        try:
            root = ET.fromstring(f"<root>{tool_content}</root>")
            for child in root:
                params[child.tag] = child.text.strip() if child.text else ""
        except ET.ParseError:
            print(f"Error parsing tool parameters: {tool_content}")
            return None

        return {tool_name: params}

    def _execute_tool(self, tool_name: str, params: Dict[str, str]) -> str:
        """Execute a tool with the given parameters and return the result."""
        print(f"\nExecuting tool: {tool_name}")
        print(f"Parameters: {params}")

        if tool_name == "web_search":
            query = params.get("query")
            if not query:
                return "Error: No query provided for web search"

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=3):
                    title = r.get("title", "No title")
                    url = r.get("link", r.get("url", "No URL"))
                    body = r.get("body", r.get("snippet", "No description"))
                    results.append(f"- {title}\n  URL: {url}\n  {body}")

            return "Search results:\n" + "\n\n".join(results)

        elif tool_name == "attempt_completion":
            result = params.get("r", "")
            command = params.get("command")

            response = result
            if command:
                response += f"\n\nCommand to execute: {command}"
            return response

        return f"Unknown tool: {tool_name}"

    def process_message(self, user_input: str) -> List[str]:
        """Process a user message and return a list of responses (assistant + tool results)."""
        self.messages.append({"role": "user", "content": user_input})
        responses = []
        continue_conversation = True

        while continue_conversation:
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, temperature=0.7, stream=True
            )

            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield ("assistant", content)
            # Add a newline after each complete assistant response if not empty
            if full_response.strip():
                yield ("assistant", "\n")

            self.messages.append({"role": "assistant", "content": full_response})

            # Check for tool calls
            tool_call = self._parse_tool_call(full_response)
            if tool_call:
                tool_name = list(tool_call.keys())[0]
                tool_params = tool_call[tool_name]

                tool_result = self._execute_tool(tool_name, tool_params)
                yield ("tool", tool_result)

                # Stop if attempt_completion is called
                if tool_name == "attempt_completion":
                    continue_conversation = False
                else:
                    self.messages.append(
                        {"role": "user", "content": f"Tool result: {tool_result}"}
                    )
            else:
                # If no tool call, add a prompt to encourage task completion
                self.messages.append({
                    "role": "user",
                    "content": "Please continue with the task. When you're finished, use the attempt_completion tool to indicate completion."
                })
