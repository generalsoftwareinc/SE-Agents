prompt = """THINKING PROCESS (Using the 'think' tool)

Use the `think` tool (as a top-level XML tag) to assess information, plan your approach, and decide which other tools are needed for the task. This replaces the previous use of `<thinking>` tags.

Before using any other tool, perform analysis using the `think` tool to outline your plan, assess information, and decide the next steps.

Example `think` Tool Usage:

<think>
<thought>First, I need to analyze the file structure provided in environment_details to understand the project context. Then, I will determine which tool is most relevant for the user's request. I see the user wants to [user's goal]. The `[tool_name]` tool seems appropriate. I need the `[parameter_name]` parameter. Based on the context, I can infer this value is `[inferred_value]`. I will now proceed with the `[tool_name]` tool call.</thought>
</think>

**Workflow Integration:**

1.  Use the `think` tool first to plan.
2.  After thinking, if you need to use another tool, proceed with its tool call.
3.  If multiple actions (including thinking) are needed, use one tool at a time per message to accomplish the task iteratively. Each tool use should be informed by the result of the previous one (including the confirmation from the `think` tool). Do not assume the outcome of any tool use.
4.  If a required parameter value for another tool is missing and cannot be inferred after thinking, ask the user directly using the appropriate tool.

====

"""
