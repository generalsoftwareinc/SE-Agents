import inspect
import re
import xml.etree.ElementTree as ET
from calendar import c
from typing import AsyncGenerator, Dict, List, Optional, Union

from httpx import stream
from openai import AsyncOpenAI

from se_agents.schemas import ResponseEvent
from se_agents.system_prompt import build_system_prompt
from se_agents.tools import OpenAIVisionTool, Tool, VisionBaseTool

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
        add_tool_instructions: bool = True,
        add_default_rules: bool = True,
        add_default_objective: bool = True,
        # Prompt config additions
        add_think_instructions: bool = False,
        add_final_output_instructions: bool = False,
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
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        # Tool config
        self.tools = tools or []

        # Prompt config
        self._custom_description = description
        self._custom_rules = rules
        self._custom_objective = objective
        self._custom_instructions = instructions
        self._additional_context = additional_context
        self.add_tool_instrutions = add_tool_instructions
        self.add_default_rules = add_default_rules
        self.add_default_objective = add_default_objective
        self.add_think_instructions = add_think_instructions
        self.add_final_output_instructions = add_final_output_instructions

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
            add_think_instructions=self.add_think_instructions,
            add_final_output_instructions=self.add_final_output_instructions,
        )
        return {
            "role": "system",
            "content": full_prompt,
        }

    def _parse_tool_call(
        self, message: str
    ) -> tuple[Optional[str], Optional[Dict[str, str]], Optional[str], Optional[str]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Searches for a top-level XML tag matching a known tool name.

        Returns:
            tuple: (tool_name, params_dict, error_message, raw_tool_call_xml)
                - tool_name: The name of the tool called, or None if not found/parsed
                - params_dict: Dictionary with parameters, or None if parsing failed
                - error_message: Error message if parsing failed, or None if successful
                - raw_tool_call_xml: The raw XML string of the tool call, or None if not found/parsed
        """
        raw_tool_call_xml = None
        tool_name = None
        tool_call_content = None
        tool = None  # Keep tool variable for later use

        for t in self.tools:
            m = re.search(rf"<{t.name}>(.*?)</{t.name}>", message, re.DOTALL)
            if m:
                raw_tool_call_xml = m.group(0)
                tool_call_content = m.group(1).strip()
                tool_name = t.name
                tool = t  # Assign the found tool
                break

        if not raw_tool_call_xml:
            # No tool call found matching a known tool name
            return None, None, None, None

        try:
            # Parse the extracted content using ElementTree
            root = ET.fromstring(raw_tool_call_xml)

            # Extract parameters
            params = {}
            for child in root:
                params[child.tag] = child.text.strip() if child.text else ""

            # Validate required parameters
            missing_required = []
            # Use the 'tool' variable found in the loop
            for p_name, p_details in tool.parameters.items():
                if p_details.get("required", False) and p_name not in params:
                    missing_required.append(p_name)
            if missing_required:
                return (
                    None,
                    None,
                    f"Missing required parameters for {tool_name}: {', '.join(missing_required)}",
                    raw_tool_call_xml,
                )

            # Parameter type validation could be added here if needed

            return tool_name, params, None, raw_tool_call_xml

        except ET.ParseError as e:
            print(f"DEBUG _parse_tool_call: XML parse error: {e}")
            return (
                None,
                None,
                f"Malformed XML for tool call {tool_name}: {e}",
                raw_tool_call_xml,
            )
        except Exception as e:
            print(f"DEBUG _parse_tool_call: Unexpected error during parsing: {e}")
            return (
                None,
                None,
                f"Error parsing tool call {tool_name}: {e}",
                raw_tool_call_xml,
            )

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
                if isinstance(tool, OpenAIVisionTool):
                    result = await tool.execute(
                        client=self.client, model=self.model, **params
                    )
                else:
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
        only_text_token_count = sum(
            len(message["content"].split())
            for message in self.messages
            if isinstance(message["content"], str)
        )

        messages_with_attachment = [
            msg for msg in self.messages if isinstance(msg["content"], list)
        ]
        messages_with_attachment_token_count = 0
        for msg in messages_with_attachment:

            for content in msg["content"]:

                if content["type"] == "text":
                    messages_with_attachment_token_count += len(content["text"].split())
                elif content["type"] == "image_url":
                    messages_with_attachment_token_count += len(content["image_url"]["url"].split())

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
        async for chunk in response:
            text = chunk.choices[0].delta.content
            if not text:
                continue
            for token in self._split_tokens(text):
                yield token

    async def run_stream(
        self, user_input: str, image_urls: Optional[List[str]] = None
    ) -> AsyncGenerator[ResponseEvent, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles the conversation loop, including tool calls and user interactions.
        For the ask_followup_question tool, it yields a special response type that signals
        the main loop to get user input and then continue the conversation with that input.
        """

        if image_urls and not any(
            [isinstance(tool, VisionBaseTool) for tool in self.tools]
        ):
            print("=== Appending image to messages ===")
            image_dicts = [
                {"type": "image_url", "image_url": {"url": url}} for url in image_urls
            ]
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_input},
                        *image_dicts,
                    ],
                }
            )
        else:
            self.messages.append({"role": "user", "content": user_input})

        # first message input is not handled by Runner
        self._truncate_context_window()
        response = await self.client.chat.completions.create(
            model=self.model, messages=self.messages, stream=True
        )

        full_response = ""
        tool_name = None
        params = None
        error_message = None
        raw_tool_xml = None
        halted = False
        tag_found = False
        tool_found = False
        tokens_since_halted = 0
        halted_tokens = ""

        ## New experimental feature: streaming tool responses
        tool_streaming = False
        stream_param = None

        async for content in self._token_stream(response):
            full_response += content
            if "<" in content:
                halted = True

            # Normal response when not halted
            if not halted:
                yield ResponseEvent(type="response", content=content)
                continue

            # Accumulate after halt
            tokens_since_halted += 1
            halted_tokens += content

            # Flush buffer if no tag detected within 5 tokens
            if tokens_since_halted > 5 and not tag_found:
                yield ResponseEvent(type="response", content=halted_tokens)
                halted = False
                tokens_since_halted = 0
                halted_tokens = ""
                continue

            # Detect start of tool tag
            if not tag_found:
                for t in self.tools:
                    if f"<{t.name}>" in full_response:
                        tag_found = True
                        if t.stream:
                            tool_streaming = True
                            stream_param = t.param_stream
                        break

            # Handle complete tags
            if tag_found:
                check_set = {"<", ">", "/"}
                if tool_streaming:
                    if f"<{stream_param}>" in full_response and not check_set & {
                        content.strip()
                    }:
                        yield ResponseEvent(type="response", content=content)
                    if "</" in full_response:
                        tool_streaming = False
                # print("----- Tag found -----")
                # print("Starting to parse tool call")
                if not tool_found:
                    for t in self.tools:
                        # print(f"Checking for </{t.name}>")
                        # print(f"Full response at this point: {full_response}")
                        if f"</{t.name}>" in full_response:
                            tag_found = False
                            tool_name, params, error_message, raw_tool_xml = (
                                self._parse_tool_call(full_response)
                            )
                            break
                    if error_message:
                        error_payload = error_message
                        if raw_tool_xml:
                            error_payload += f"\nRaw XML:\n{raw_tool_xml}"
                        yield ResponseEvent(
                            type="tool_error",
                            content=f"<tool_error>\n{error_payload}\n</tool_error>\n",
                        )
                        return
                    if raw_tool_xml:
                        tool_found = True
                        yield ResponseEvent(
                            type="tool_call", content=raw_tool_xml or ""
                        )
                        return

                # Removed thinking block handling - will be handled as a normal tool call

        # --- After the stream loop finishes ---
        print(f"Stream finished. Final accumulated content: {full_response}")

        if tag_found and not tool_found:
            print("Stream ended with an unclosed tool call.")
            yield ResponseEvent(
                type="tool_error",
                content=f"<tool_error>\nStream ended unexpectedly within a tool call. Closing tag not found. Incomplete XML:\n{halted_tokens}\n</tool_error>\n",
            )
        elif halted and not tool_found and not tag_found:
            # If we halted (saw '<') but never found a complete tag or ended inside one, yield the buffered content as response
            print("----- Stream ended after halting, flushing remaining buffer -----")
            print(halted_tokens)
            print("-------------------------------------------------------")
            yield ResponseEvent(type="response", content=halted_tokens)

        # Agent no longer appends assistant responses to its own history

    def _get_tool_by_name(self, tool_name: str) -> Optional[Tool]:
        """Return the tool with the given name from self.tools, or None if not found."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
