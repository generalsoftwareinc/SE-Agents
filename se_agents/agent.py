import inspect
import re
import xml.etree.ElementTree as ET
from typing import AsyncGenerator, Dict, List, Optional, Union

from openai import Client

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

        try:
            tool._process_parameters(**params)
        except Exception as e:
            return str(e), False

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

    def _split_tokens(self, content: str) -> List[str]:
        """Split LLM delta content into elementary tokens for streaming."""
        return re.findall(r"(<|>|\s+|[^\s<>]+)", content)

    async def _token_stream(self, response) -> AsyncGenerator[str, None]:
        """Flatten the LLM streaming response into a stream of tokens."""
        for chunk in response:
            text = chunk.choices[0].delta.content
            if not text:
                continue
            for token in self._split_tokens(text):
                yield token

    async def _filter_thinking(
        self, token_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[ResponseEvent, None]:
        """
        Filter the token stream to handle <thinking> blocks.

        When a complete thinking block is detected, emit it as a thinking event.
        All other tokens are emitted as response events.
        """
        buffer = ""
        halted = False
        thinking_buffer = ""

        async for token in token_stream:
            buffer += token

            # If we see a start tag, begin accumulating
            if not halted and "<thinking>" in buffer:
                halted = True

            # Accumulate tokens while in halted mode
            if halted:
                thinking_buffer += token
                # Check if thinking block is complete
                if "</thinking>" in buffer:
                    # Emit the complete thinking block
                    yield ResponseEvent(
                        type="thinking",
                        content=(
                            thinking_buffer
                            if thinking_buffer.endswith("\n")
                            else thinking_buffer + "\n"
                        ),
                    )
                    # Reset buffers and state
                    halted = False
                    thinking_start = buffer.find("<thinking>")
                    thinking_end = buffer.find("</thinking>") + len("</thinking>")
                    # Remove the thinking block from the main buffer
                    buffer = buffer[:thinking_start] + buffer[thinking_end:]
                    thinking_buffer = ""
            else:
                # If not halted, pass through tokens immediately
                yield ResponseEvent(type="response", content=token)

    async def _filter_tool_calls(
        self, event_stream: AsyncGenerator[ResponseEvent, None]
    ) -> AsyncGenerator[ResponseEvent, None]:
        """
        Filter response events to handle <tool_call> blocks.

        When a complete tool call is detected, parse and emit it, then stop the stream.
        """
        buffer = ""
        halted = False
        tool_buffer = ""

        async for event in event_stream:
            # Only process response events (pass thinking events through unchanged)
            if event.type == "thinking":
                yield event
                continue

            token = event.content
            buffer += token

            # If we see a start tag, begin accumulating
            if not halted and "<tool_call>" in buffer:
                halted = True

            # Accumulate tokens while in halted mode
            if halted:
                tool_buffer += token
                # Check if tool call is complete
                if "</tool_call>" in buffer:
                    # Parse the complete tool call
                    tool_call, error_message, raw_tool_xml = self._parse_tool_call(
                        buffer
                    )

                    if error_message:
                        yield ResponseEvent(
                            type="tool_error",
                            content=f"<tool_error>\n{error_message}\n</tool_error>\n",
                        )

                    if tool_call:
                        yield ResponseEvent(
                            type="tool_call", content=raw_tool_xml  # Use raw XML here
                        )
                        return  # Stop the stream after a tool call

                    # If there was no valid tool call, reset and continue
                    halted = False
                    tool_buffer = ""
            else:
                # If not halted, pass through tokens
                yield event

        # Final newline if needed and not ending with a tag
        if buffer.strip() and not re.search(r"</[^>]+>\s*$", buffer):
            yield ResponseEvent(type="response", content="\n")

    async def run_stream(self, user_input: str) -> AsyncGenerator[ResponseEvent, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles tokenization, thinking tags, and tool calls by passing the stream
        through a series of filters that each handle a specific responsibility.
        """
        self.messages.append(
            {"role": "user", "content": user_input}
        )  # first message input is not handled by Runner
        self._truncate_context_window()

        # Create the raw LLM response stream
        response = self.client.chat.completions.create(
            model=self.model, messages=self.messages, stream=True
        )

        # Process the stream through each filter in sequence
        token_stream = self._token_stream(response)
        thinking_filtered = self._filter_thinking(token_stream)
        async for event in self._filter_tool_calls(thinking_filtered):
            yield event

    def _get_tool_by_name(self, tool_name: str) -> Optional[Tool]:
        """Return the tool with the given name from self.tools, or None if not found."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
