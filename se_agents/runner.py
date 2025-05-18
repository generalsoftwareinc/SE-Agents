from typing import AsyncGenerator, List, Optional, Union, Tuple

from se_agents.agent import Agent
from se_agents.schemas import ResponseEvent, ToolCallResponseEvent, TextResponseEvent, ToolResponseEvent, ToolErrorEvent


class Runner:
    def __init__(self, agent: Agent, enforce_final: bool = False):
        self.agent = agent
        self.enforce_final = enforce_final
    
    async def _execute_tool_and_create_response(self, tool_name: str, params: dict) -> Tuple[Union[ToolResponseEvent, ToolErrorEvent], bool, Optional[str]]:
        """Execute a tool and create an appropriate response event.
        
        Returns:
            - The response event (either ToolResponseEvent or ToolErrorEvent)
            - Whether this was a final_output call
            - The final output content if applicable, otherwise None
        """
        result, success = await self.agent._execute_tool(tool_name, params)
        
        is_final = False
        final_content = None
        
        if success:
            response_event = ToolResponseEvent.from_execution(result, tool_name)
            if tool_name == "final_output":
                is_final = True
                final_content = result
        else:
            response_event = ToolErrorEvent.from_error(f"Tool execution failed: {result}", None, tool_name)
        
        return response_event, is_final, final_content

    async def run(
        self, user_input: str, image_urls: Optional[List[str]] = None
    ) -> AsyncGenerator[Union[ResponseEvent, TextResponseEvent, ToolCallResponseEvent, ToolResponseEvent, ToolErrorEvent], None]:
        """
        Execute a query through the Agent, handle tool calls, and yield events.
        If enforce_final is True, it buffers 'response' events and only yields
        the final result from the 'final_output' tool. If the tool is not called,
        it re-prompts the agent.
        """
        next_input = user_input

        while True:
            tool_event = False
            final_output = False
            buffered_response = ""
            final_output_result_content = None

            async for event in self.agent.run_stream(next_input, image_urls):
                # Handle specialized ToolCallResponseEvent
                if isinstance(event, ToolCallResponseEvent):
                    tool_event = True
                    yield event
                    
                    # Process the tool call
                    response_event, is_final, final_content = await self._execute_tool_and_create_response(
                        event.tool_name, event.parameters
                    )
                    
                    yield response_event
                    next_input = response_event.content
                    
                    if is_final:
                        final_output = True
                        final_output_result_content = final_content
                    
                    break
                
                # Handle legacy tool_call event
                elif event.type == "tool_call":
                    tool_event = True
                    yield event
                    
                    # Parse the tool call from XML
                    tool_name, params, error_msg, raw_xml = self.agent._parse_tool_call(
                        event.content
                    )
                    
                    if error_msg or not tool_name:
                        # Handle parsing error
                        error_event = ToolErrorEvent.from_error(
                            f"Runner failed to parse tool call: {error_msg or 'Parse failure'}", 
                            raw_xml
                        )
                        yield error_event
                        next_input = error_event.content
                        break
                    
                    # Process the tool call
                    response_event, is_final, final_content = await self._execute_tool_and_create_response(
                        tool_name, params
                    )
                    
                    yield response_event
                    next_input = response_event.content
                    
                    if is_final:
                        final_output = True
                        final_output_result_content = final_content
                    
                    break
                
                # Handle tool_error events
                elif event.type == "tool_error":
                    tool_event = True
                    if isinstance(event, ToolErrorEvent):
                        yield event
                    else:
                        # Convert legacy error event to specialized class
                        error_event = ToolErrorEvent.from_error("Tool error", event.content)
                        yield error_event
                    next_input = event.content
                    break
                
                # Handle text response events
                elif event.type == "response":
                    if self.enforce_final:
                        buffered_response += event.content
                    else:
                        if isinstance(event, TextResponseEvent):
                            yield event
                        else:
                            # Convert legacy response event to specialized class
                            yield TextResponseEvent.from_text(event.content)
            
            # Handle enforce_final logic
            if self.enforce_final:
                if final_output:
                    if final_output_result_content is not None:
                        yield TextResponseEvent.from_text(final_output_result_content)
                    break
                elif tool_event:
                    continue
                else:
                    print("No final output found, retrying with feedback")
                    reprompt_message = "You did not conclude the task using the 'final_output' tool. Please provide the final result using the 'final_output' tool now."
                    next_input = f"<feedback>\n{reprompt_message}\n</feedback>\n"
                    continue
            else:
                if final_output or not tool_event:
                    break