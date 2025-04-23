import inspect
import re
import xml.etree.ElementTree as ET
from pprint import pprint
from typing import AsyncGenerator, Dict, List, Optional, Union

from openai import Client

from se_agents.prompts.additional_context import prompt as additional_context_prompt
from se_agents.prompts.description import prompt as description_prompt
from se_agents.prompts.tool_calling import prompt as tool_calling_prompt
from se_agents.prompts.tool_calling import tools_placeholder
from se_agents.schemas import ResponseEvent
from se_agents.system_prompt import build_system_prompt
from se_agents.tools import Tool

TOKEN_LIMIT = 80000


class Agent:
    def __init__(
        self,
        # Core agent config
        name: str = None,
        token_limit: int = TOKEN_LIMIT,
        # OpenAI config
        api_key: str = None,
        model: str = None,
        base_url: str = None,
        # Tool config
        tools: List[Tool] = None,
        # Prompt config
        description: Union[str, None] = None,
        rules: Union[str, List[str], None] = None,
        objective: Union[str, List[str], None] = None,
        instructions: Union[str, List[str], None] = None,
        additional_context: Union[str, List[str], None] = None,
        add_tool_instrutions: bool = True,
        add_default_rules: bool = True,
        add_default_objective: bool = True,
        # Message config
        initial_messages: Optional[List[Dict[str, str]]] = None,
        # Verbose config
        verbose: bool = False,
    ):
        # Core agent config
        self.name = name
        self.token_limit = token_limit

        # Verbose config
        self.verbose = verbose

        # OpenAI config
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = Client(api_key=api_key, base_url=base_url)

        # Tool config
        self.tools = tools or []

        # Prompt config
        self._custom_description = description
        self._custom_rules = rules
        self._custom_objective = objective
        self.add_tool_instrutions = add_tool_instrutions
        self.add_default_rules = add_default_rules
        self.add_default_objective = add_default_objective
        self._custom_instructions = instructions
        self._additional_context = additional_context

        # Message config
        system_message = self._add_system_prompt()
        if initial_messages:
            self.messages: List[Dict[str, str]] = [system_message] + initial_messages
        else:
            self.messages: List[Dict[str, str]] = [system_message]

        # Debug output
        if self.verbose:
            print("--- Initial System Prompt (Processed) ---")
            print(self.messages[0]["content"])
            print("---------------------------------------")
            if initial_messages:
                print("--- Initial Conversation Context ---")
                for msg in self.messages[1:]:
                    print(f"{msg['role'].capitalize()}: {msg['content'][:100]}...")
                print("------------------------------------")

    def _section_to_str(self, section):
        if section is None:
            return ""
        if isinstance(section, list):
            return "\n".join(section)
        return section

    def _add_system_prompt(self):
        full_prompt = build_system_prompt(
            description=self._custom_description,
            add_tool_instructions=self.add_tool_instrutions,
            tools=self.tools,
            custom_rules=self._custom_rules,
            add_default_rules=self.add_default_rules,
            custom_objective=self._custom_objective,
            add_default_objective=self.add_default_objective,
            additional_context=self._additional_context,
            custom_instructions=self._custom_instructions,
        )
        return {
            "role": "system",
            "content": full_prompt,
        }

    def _parse_tool_call(
        self, message: str
    ) -> tuple[Optional[Dict[str, Dict[str, str]]], Optional[str], Optional[str]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Handles tool calls both directly in the message and inside code blocks.

        Returns:
            tuple: (tool_call_dict, error_message, raw_tool_call_xml)
                - tool_call_dict: Dictionary with tool name as key and parameters as values, or None if parsing failed
                - error_message: Error message if parsing failed, or None if successful
                - raw_tool_call_xml: The raw XML string of the tool call, or None if not found/parsed
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
                raw_tool_call_xml = tool_call_match.group(
                    0
                )  # Capture the full <tool_call>...</tool_call>
            else:
                return (
                    None,
                    "Malformed tool call format. Please use the format: <tool_call><tool_name>...</tool_name></tool_call>",
                    None,
                )
        else:
            # No <tool_call> tag found
            return None, None, None

        # Use the extracted tool_name and tool_content
        tool = self._get_tool_by_name(tool_name)
        if not tool:
            # Add raw_tool_call_xml here as the third return value
            return None, f"Unknown tool: {tool_name}", raw_tool_call_xml

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
                    raw_tool_call_xml,
                )

            params = {
                child.tag: child.text.strip() if child.text else "" for child in root
            }

        except ET.ParseError as e:
            return (
                None,
                f"Malformed XML in tool call: {str(e)} \nPlease check the format.",
                raw_tool_call_xml,
            )

        return {tool_name: params}, None, raw_tool_call_xml

    async def _execute_tool(
        self, tool_name: str, params: Dict[str, str]
    ) -> tuple[str, bool]:
        """Execute a tool with the given parameters and return the result and success status.

        This method can handle both synchronous and asynchronous tools.

        Returns:
            tuple: (result, success)
                - result: The tool execution result or error message
                - success: True if execution was successful, False if there were errors
        """
        tool = self._get_tool_by_name(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}", False

        errors = tool.validate_parameters(params)
        if errors:
            return "\n".join(errors), False

        try:
            if inspect.iscoroutinefunction(tool.execute):
                result = await tool.execute(**params)
            else:
                result = tool.execute(**params)

            if not isinstance(result, str):
                result = str(result)

            return result, True
        except Exception as e:
            return f"Tool error: {str(e)}", False

    @property
    def total_token_count(self) -> int:
        """Calculate the total number of words in the content of all messages."""
        return sum(len(message["content"].split()) for message in self.messages)

    def _truncate_context_window(self):
        # Only pop messages (except system and last) until under token limit.
        while self.total_token_count > self.token_limit and len(self.messages) > 2:
            if self.verbose:
                print(
                    f"==={self.total_token_count} > {self.token_limit}, removing oldest message (except system and last)==="
                )
            # Always preserve the first (system) and last message
            del self.messages[1]
        if self.verbose:
            print(f"===CONTEXT WINDOW TOKEN COUNT: {self.total_token_count}===")

    async def run_stream(self, user_input: str) -> AsyncGenerator[ResponseEvent, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles the conversation loop, including tool calls and user interactions.
        For the ask_followup_question tool, it yields a special response type that signals
        the main loop to get user input and then continue the conversation with that input.
        """
        self.messages.append({"role": "user", "content": user_input})
        continue_conversation = True

        while continue_conversation:
            self._truncate_context_window()
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, stream=True
            )

            full_response = ""
            tool_call, error_message, raw_tool_xml = (
                None,
                None,
                None,
            )  # Add raw_tool_xml
            halted = False
            tag_found = False
            thinking_found = False
            tool_found = False
            tokens_since_halted = 0
            halted_tokens = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    full_content = chunk.choices[0].delta.content
                    parts = re.findall(r"(<|>|\s+|[^\s<>]+)", full_content)
                    # print(f"CONTENT: '{full_content}' ===> PARTS: '{parts}'\n")
                    for content in parts:
                        if "ing>" in content:
                            print(f"CONTENT: {content}")
                            print(f"CONTENT: '{full_content}' ===> PARTS: '{parts}'\n")
                        full_response += content

                        if "<" in content:
                            halted = True

                        if halted:
                            tokens_since_halted += 1
                            halted_tokens += content

                            if tokens_since_halted > 5 and not tag_found:
                                halted = False
                                tokens_since_halted = 0
                                content = halted_tokens
                                tokens_since_halted = 0
                                yield ResponseEvent(
                                    type="response",
                                    content=halted_tokens,
                                )
                                halted_tokens = ""
                            elif (
                                "<tool_call>" in full_response
                                or "<thinking>" in full_response
                            ) and not tag_found:
                                tag_found = True

                            if tag_found:
                                if "</tool_call>" in full_response and not tool_found:
                                    tag_found = False
                                    (
                                        tool_call,
                                        error_message,
                                        raw_tool_xml,
                                    ) = self._parse_tool_call(full_response)

                                    if error_message:
                                        halted = False
                                        tokens_since_halted = 0
                                        halted_tokens = ""
                                        yield ResponseEvent(
                                            type="tool_error",
                                            content=f"<tool_error>{content}</tool_error>",
                                        )
                                    if tool_call:
                                        tool_found = True
                                        halted = False
                                        tokens_since_halted = 0
                                        halted_tokens = ""
                                        yield ResponseEvent(
                                            type="tool_call",
                                            content=raw_tool_xml,  # Use raw XML here
                                        )

                                if (
                                    "</thinking>" in full_response
                                    and not thinking_found
                                ):
                                    tag_found = False
                                    thinking_found = True
                                    halted = False
                                    tokens_since_halted = 0
                                    yield ResponseEvent(
                                        type="thinking",
                                        content=halted_tokens,
                                    )
                                    halted_tokens = ""

                        else:
                            yield ResponseEvent(
                                type="response",
                                content=content,
                            )

            if full_response.strip() and not re.search(r"</[^>]+>\s*$", full_response):
                yield ResponseEvent(type="response", content="\n")

            if full_response and full_response.strip():
                self.messages.append({"role": "assistant", "content": full_response})
            else:
                continue_conversation = False
                continue

            if error_message:
                feedback = f"Tool call error: {error_message}\n\nPlease try again with the correct format."
                self.messages.append({"role": "user", "content": feedback})
                continue_conversation = True

            elif tool_call:
                tool_name = list(tool_call.keys())[0]
                tool_params = tool_call[tool_name]

                tool_result, success = await self._execute_tool(tool_name, tool_params)

                history_message_content = (
                    tool_result if isinstance(tool_result, str) else str(tool_result)
                )
                history_message = (
                    f"<tool_response>\n{history_message_content}\n</tool_response>"
                )
                if success:
                    yield ResponseEvent(type="tool_response", content=history_message)
                if not success:
                    yield ResponseEvent(type="tool_error", content=history_message)
                    tool = self._get_tool_by_name(tool_name)
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

    def _get_tool_by_name(self, tool_name: str) -> Optional[Tool]:
        """Return the tool with the given name from self.tools, or None if not found."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
