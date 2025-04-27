prompt = """FINAL OUTPUT INSTRUCTIONS

After completing all necessary actions for a step in processing the user's request (including planning and any required uses of tools), you MUST conclude the response cycle by using the `final_output`.

Provide your complete response or summary of work done for this step within the `result` parameter. This applies whether you completed a larger task or handled a simple conversational input.

Example `final_output` Tool Usage:

<final_output>
<result>
Your final result description here
</result>
</final_output>

The `final_output` tool should be used to:
1. Present the final result of your task to the user
2. Summarize the work completed in this step  
3. Provide any concluding remarks or next steps
4. Avoid leaving the conversation open-ended - make your response final and complete
"""
