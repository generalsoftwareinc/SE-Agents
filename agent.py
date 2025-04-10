import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Generator, List, Optional, Tuple, Union

from openai import Client

from schemas import AssistantMessage, ToolMessage
from system_prompt import system_prompt
from tools import DuckDuckGoSearch, Tool

TOKEN_LIMIT = 80000

class Agent:
    def __init__(
        self,
        api_key: str,
        model: str,
        tools: List[Tool] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        token_limit: int = TOKEN_LIMIT,
    ):
        self.token_limit = token_limit
        self.client = Client(api_key=api_key, base_url=base_url)
        self.model = model
        self.tools = {tool.name: tool for tool in (tools or [])}

        # Replace the tools template with the formatted tools section
        system_message = self._add_system_prompt()
        self.messages: List[Dict[str, str]] = [system_message]

    def _add_system_prompt(self):
        # Format the tools section of the system prompt
        tools_section = ""
        for tool in self.tools.values():
            # Tool header
            tools_section += f"## {tool.name}\n"
            tools_section += f"{tool.description}\n"
            tools_section += "Parameters:\n"

            # Parameters
            for name, param in tool.parameters.items():
                required = "(required)" if param.get("required", False) else ""
                tools_section += (
                    f"- {name}: {param.get('description', '')} {required}\n"
                )

            # Usage example
            tools_section += "Usage:\n"
            tools_section += f"<{tool.name}>\n"
            for name in tool.parameters:
                tools_section += f"<{name}>{name} here</{name}>\n"
            tools_section += f"</{tool.name}>\n\n"

        return {
            "role": "system",
            "content": system_prompt.replace(
                "{% for tool in tools %}\n## {{ tool.name }}\n{{ tool.description }}\nParameters:\n{% for name, param in tool.parameters.items() %}\n- {{ name }}: {{ param.description }} {% if param.required %}(required){% endif %}\n{% endfor %}\nUsage:\n<{{ tool.name }}>\n{% for name, param in tool.parameters.items() %}<{{ name }}>{{ name }} here</{{ name }}>\n{% endfor %}</{{ tool.name }}>\n\n{% endfor %}",
                tools_section,
            ),
        }

    def _parse_tool_call(
        self, message: str
    ) -> tuple[Optional[Dict[str, Dict[str, str]]], Optional[str]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Handles tool calls both directly in the message and inside code blocks.

        Returns:
            tuple: (tool_call_dict, error_message)
                - tool_call_dict: Dictionary with tool name as key and parameters as values, or None if parsing failed
                - error_message: Error message if parsing failed, or None if successful
        """
        # Look for tool calls inside code blocks first
        code_block_match = re.search(
            r"```(?:xml|tool_code)?\s*\n?(.*?)\n?```", message, re.DOTALL
        )
        if code_block_match:
            message = code_block_match.group(1)

        # Skip thinking tags - they're not tool calls
        if "<thinking>" in message or "</thinking>" in message:
            # Remove thinking tags and their content for tool parsing (case-insensitive and handles whitespace)
            message = re.sub(
                r"<\s*thinking[^>]*>.*?<\s*/\s*thinking\s*>",
                "",
                message,
                flags=re.DOTALL | re.IGNORECASE,
            )

        tool_call_match = re.search(r"<tool_call>(.*?)</tool_call>", message, re.DOTALL)
        if tool_call_match:
            tool_call_content = tool_call_match.group(1)
            tool_name_match = re.search(
                r"<([^>]+)>(.*?)</\1>", tool_call_content, re.DOTALL
            )
            if tool_name_match:
                tool_name = tool_name_match.group(1)
                tool_content = tool_name_match.group(2)
            else:
                return (
                    None,
                    "Malformed tool call format. Please use the format: <tool_call><tool_name>...</tool_name></tool_call>",
                )
        else:
            return None, None

        # Use the extracted tool_name and tool_content
        tool = self.tools.get(tool_name)
        if not tool:
            return None, f"Unknown tool: {tool_name}"

        params = {}
        try:
            temp_root_str = f"<root>{tool_content}</root>"
            root = ET.fromstring(temp_root_str)

            expected_params = set(tool.parameters.keys())
            found_tags = {child.tag for child in root}

            if not found_tags.issubset(expected_params):
                return (
                    None,
                    f"Unexpected parameters in tool call for {tool_name}. Expected: {', '.join(expected_params)}",
                )

            params = {
                child.tag: child.text.strip() if child.text else "" for child in root
            }

        except ET.ParseError as e:
            return (
                None,
                f"Malformed XML in tool call: {str(e)} \n Please check the format.",
            )

        return {tool_name: params}, None

    def _execute_tool(self, tool_name: str, params: Dict[str, str]) -> tuple[str, bool]:
        """Execute a tool with the given parameters and return the result and success status.

        Returns:
            tuple: (result, success)
                - result: The tool execution result or error message
                - success: True if execution was successful, False if there were errors
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}", False

        errors = tool.validate_parameters(params)
        if errors:
            return "Error: " + "\n".join(errors), False

        try:
            result = tool.execute(**params)
            return result, True
        except Exception as e:
            return f"Tool error: {str(e)}", False

    @property
    def total_token_count(self) -> int:
        """Calculate the total number of words in the content of all messages."""
        return sum(len(message["content"].split()) for message in self.messages)

    def _truncate_context_window(self, verbosity=False):
        while self.total_token_count > self.token_limit:
            if verbosity:
                print(
                    f"==={self.total_token_count} > {self.token_limit}, Reducing token count by truncating the longest messages==="
                )

            tpm = [len(msg["content"].split()) for msg in self.messages]
            median_token_count = sorted(tpm)[len(tpm) // 2]

            def truncate_message_content(content: str) -> str:

                tokens = content.split()

                if len(tokens) <= median_token_count:
                    return content

                percent = 20
                first_x_percent = tokens[: max(1, len(tokens) // percent)]
                last_x_percent = tokens[-max(1, len(tokens) // percent) :]
                return " ".join(first_x_percent + ["..."] + last_x_percent)

            self.messages = [
                {
                    **msg,
                    "content": truncate_message_content(msg["content"]),
                }
                for msg in self.messages
            ]

            if self.total_token_count > self.token_limit:
                if len(self.messages) <= 2:
                    print(
                        "===Unable to truncate, context window contains <= 2 messages==="
                    )
                    break
                if verbosity:
                    print(
                        f"==={self.total_token_count} > {self.token_limit}, Reducing token count by eliminating older messages==="
                    )

                conversation_messages = self.messages[1:]
                user_messages = [msg for msg in self.messages if msg.role == "user"]
                latest_user_message = user_messages[-1]
                conversation_messages = [
                    msg
                    for msg in self.conversation_messages
                    if msg.role != "user" or msg == latest_user_message
                ]

                if conversation_messages[0]["role"] != "user":
                    conversation_messages.pop(0)
                else:
                    conversation_messages.pop(1)

                self.messages = [
                    self._add_system_prompt(),
                    *conversation_messages,
                ]
                print(self.messages[0])

        if verbosity:
            print(f"===CONTEXT WINDOW TOKEN COUNT: {self.total_token_count}===")

    def process_message(
        self, user_input: str, stream: bool = False
    ) -> Generator[Tuple[str, str], None, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles the conversation loop, including tool calls and user interactions.
        For the ask_followup_question tool, it yields a special response type that signals
        the main loop to get user input and then continue the conversation with that input.
        """
        self.messages.append({"role": "user", "content": user_input})
        continue_conversation = True
        print(self.messages[0], self.messages[-1])

        while continue_conversation:
            self._truncate_context_window(verbosity=True)
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, stream=stream
            )

            full_response = ""
            if stream:
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield AssistantMessage(role="assistant", content=content)
                if full_response.strip() and not re.search(
                    r"</[^>]+>\s*$", full_response
                ):
                    yield AssistantMessage(role="assistant", content="\n")
            else:
                full_response = response.choices[0].message.content
                if full_response:
                    yield AssistantMessage(role="assistant", content=full_response)
                    if not re.search(r"</[^>]+>\s*$", full_response):
                        yield AssistantMessage(role="assistant", content="\n")

            if full_response and full_response.strip():
                self.messages.append({"role": "assistant", "content": full_response})
            else:
                continue_conversation = False
                continue

            tool_call, error_message = self._parse_tool_call(full_response)

            if error_message:
                feedback = f"Tool call error: {error_message}\n\nPlease try again with the correct format."
                yield ToolMessage(role="tool", content=feedback)
                self.messages.append({"role": "user", "content": feedback})
                continue_conversation = True

            elif tool_call:
                tool_name = list(tool_call.keys())[0]
                tool_params = tool_call[tool_name]

                tool_result, success = self._execute_tool(tool_name, tool_params)

                yield ToolMessage(role="tool", content=tool_result)

                history_message = f"<tool_result>\n{tool_result}\n</tool_result>"
                if not success:
                    tool = self.tools.get(tool_name)
                    if tool:
                        param_info = "\n".join(
                            [
                                f"- {name}: {config.get('description', '')} ({'required' if config.get('required') else 'optional'}, type: {config.get('type', 'string')})"
                                for name, config in tool.parameters.items()
                            ]
                        )
                        hint = f"\nPlease try again with the correct parameters for {tool_name}:\n{param_info}"
                        history_message += f"\n\n{hint}"

                self.messages.append({"role": "user", "content": history_message})

                continue_conversation = True

            else:
                continue_conversation = False
