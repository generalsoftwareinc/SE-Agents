from typing import AsyncGenerator, Dict, Optional

from se_agents.agent import Agent
from se_agents.schemas import ResponseEvent


class Runner:
    def __init__(self, agent: Agent, enforce_final: bool = False):
        self.agent = agent
        self.enforce_final = enforce_final

    async def run(self, user_input: str) -> AsyncGenerator[ResponseEvent, None]:
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

            async for event in self.agent.run_stream(next_input):

                if event.type == "tool_call":
                    tool_event = True
                    yield event

                    tool_call_dict, error_msg, raw_xml = self.agent._parse_tool_call(
                        event.content
                    )

                    if error_msg or not tool_call_dict:
                        error_content = f"<tool_error>\nRunner failed to parse agent's yielded tool_call XML: {error_msg or 'Parse failure'}\nRaw XML:\n{raw_xml}\n</tool_error>\n"
                        yield ResponseEvent(type="tool_error", content=error_content)
                        next_input = error_content
                        break

                    tool_name = next(iter(tool_call_dict))
                    params = tool_call_dict[tool_name]

                    result, success = await self.agent._execute_tool(tool_name, params)

                    if success:
                        tool_response_content = (
                            f"<tool_response>\n{result}\n</tool_response>\n"
                        )
                        yield ResponseEvent(
                            type="tool_response", content=tool_response_content
                        )
                        next_input = tool_response_content
                        if tool_name == "final_output":
                            final_output = True
                            final_output_result_content = result
                    else:
                        error_content = f"<tool_error>\nTool execution failed: {result}\n</tool_error>\n"
                        yield ResponseEvent(type="tool_error", content=error_content)
                        next_input = error_content

                    break

                elif event.type == "tool_error":
                    tool_event = True
                    yield event
                    next_input = event.content
                    break

                elif event.type == "response":
                    if self.enforce_final:
                        buffered_response += event.content
                    else:
                        yield event

            if self.enforce_final:
                if final_output:
                    if final_output_result_content is not None:
                        yield ResponseEvent(
                            type="response", content=final_output_result_content
                        )
                    break
                elif tool_event:
                    continue
                else:
                    print("No final output found, retrying with feedback")
                    reprompt_message = "You did not conclude the task using the 'final_output' tool. Please provide the final result using the 'final_output' tool now."
                    next_input = f"<feedback>\n{reprompt_message}\n</feedback>\n"
                    continue
            else:
                if not tool_event:
                    break
