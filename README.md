## TO-DO:

- [x] Modiy Agent init to modify different parts of the system_prompt. This should follow the style of Agno with an API like: add_default_rules: boolean, rules: list[str], etc.
- [ ] Migrate fetch page and web search tools to Exa.ai
- [x] Implement Runner class pattern. This will leave the Agent just to parsing the stream and yielding events, Runner executes tools and handles the loop.
- [ ] Limit agent loop iterations to n. This must include not only the logic in the loop, but also prompt the model to finish its work.

## Runner execution:
- User Input: A user sends a query (e.g., "What's the capital of France?") to the Runner component.
- Agent Init: The Runner component initializes the Agent instance with the user's input. It asynchronously calls the Agent's run_stream method, passing the user's input as a parameter.
- Tool Call: The Agent's run_stream method yields a tool_call event, which contains the tool name and parameters. Agent loop paused.
- Tool Call: The Runner yields a tool_call event, which contains the tool name and parameters. It records the tool call in the Agent's memory.
- Tool Execution: The Runner resumes the Agent loop. The Agent executes the tool with the given parameters and yields a tool_response event, which contains the tool's result.
- Tool Execution: The Runner yields a tool_response event, which contains the tool's result. It records the tool's result in the Agent's memory.
- Agent Final Answer: The Runner resumes the Agent loop. The Agent sends the tool's response to the LLM. The LLM generates chunk by chunk and the Agent yields response events, which contain the LLM's generated text.
- Agent Final Answer: The Runner yields response events, which contain the LLM's generated text. At the end of this events, if no other tool_call or tool_response events are yielded, the Runner yields a final_answer event, which contains the complete answer, plus potentially other run information (like context used in total tokens count sent to the LLM).
