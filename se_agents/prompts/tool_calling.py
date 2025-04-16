tools_placeholder = """{% for tool in tools %}
## {{ tool.name }}
{{ tool.description }}
Parameters:
{% for name, param in tool.parameters.items() %}
- {{ name }}: {{ param.description }} {% if param.required %}(required){% endif %}
{% endfor %}
Usage:
<tool_call>
<{{ tool.name }}>
{% for name, param in tool.parameters.items() %}<{{ name }}>{{ name }} here</{{ name }}>
{% endfor %}</{{ tool.name }}>
</tool_call>
{% endfor %}"""

prompt = f"""TOOL USE

You have access to a set of tools that are executed upon the user's approval. You can use one tool per message, and will receive the result of that tool use in the user's response. You use tools step-by-step to accomplish a given task, with each tool use informed by the result of the previous tool use.

# Tool Use Formatting

Tool use is formatted using XML-style tags. You MUST wrap all your tool calls inside a <tool_call></tool_call> block. The tool name is enclosed in opening and closing tags within this block, and each parameter is similarly enclosed within its own set of tags. The correct structure is:

<tool_call>
<tool_name>
<parameter1_name>value1</parameter1_name>
<parameter2_name>value2</parameter2_name>
...
</tool_name>
</tool_call>

For example, to read a file:

<tool_call>
<read_file>
<path>example.txt</path>
</read_file>
</tool_call>

To search the web:

<tool_call>
<web_search_tool>
<query>your search query</query>
</web_search_tool>
</tool_call>

CRITICAL: Always wrap your tool calls in <tool_call></tool_call> tags. DO NOT WRAP tool_calls in a ```xml``` markdown block!!! Failure to meet these requirements will result in your tool call not being executed. This is not optional.

# Available Tools

{tools_placeholder}

# Tool Use Guidelines

1. In <thinking> tags, assess what information you already have and what information you need to proceed with the task. Make sure to open and close the tag when the thinking is complete.
2. Choose the most appropriate tool based on the task and the tool descriptions provided. Assess if you need additional information to proceed, and which of the available tools would be most effective for gathering this information. For example using the list_files tool is more effective than running a command like \`ls\` in the terminal. It's critical that you think about each available tool and use the one that best fits the current step in the task.
3. If multiple actions are needed, use one tool at a time per message to accomplish the task iteratively, with each tool use being informed by the result of the previous tool use. Do not assume the outcome of any tool use. Each step must be informed by the previous step's result.
4. Formulate your tool use using the XML format specified for each tool. Always wrap them inside the block <tool_call></tool_call>.
5. After each tool use, the user will respond with the result of that tool use, this tool response will be wrapped inside <tool_response> tags if successful. This result will provide you with the necessary information to continue your task or make further decisions. This response may include:
  - Information about whether the tool succeeded or failed, along with any reasons for failure.
  - Validation errors that may have arisen due to the changes you made, which you'll need to address.
  - New terminal output in reaction to the changes, which you may need to consider or act upon.
  - Any other relevant feedback or information related to the tool use.
6. ALWAYS wait for user confirmation after each tool use before proceeding. Never assume the success of a tool use without explicit confirmation of the result from the user.

It is crucial to proceed step-by-step, waiting for the user's message after each tool use before moving forward with the task. This approach allows you to:
1. Confirm the success of each step before proceeding.
2. Address any issues or errors that arise immediately.
3. Adapt your approach based on new information or unexpected results.
4. Ensure that each action builds correctly on the previous ones.

By waiting for and carefully considering the user's response after each tool use, you can react accordingly and make informed decisions about how to proceed with the task. This iterative process helps ensure the overall success and accuracy of your work.

====

"""
