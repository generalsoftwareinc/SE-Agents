from se_agents.prompts.additional_context import prompt as additional_context_prompt
from se_agents.prompts.custom_instructions import prompt as custom_instructions_template
from se_agents.prompts.description import prompt as description_prompt
from se_agents.prompts.final_output import prompt as final_output_prompt
from se_agents.prompts.objective import prompt as objective_prompt
from se_agents.prompts.rules import prompt as rules_prompt
from se_agents.prompts.think import prompt as think_prompt
from se_agents.prompts.tool_calling import prompt as tool_calling_prompt


def insert_custom_instructions(section_prompt, custom_instructions):
    """
    Inserts custom instructions before the '====' delimiter in the section prompt.
    If no delimiter is found, appends custom instructions at the end.
    """
    delimiter = "===="
    if custom_instructions:
        idx = section_prompt.find(delimiter)
        if idx != -1:
            before = section_prompt[:idx].rstrip()
            after = section_prompt[idx:]
            return f"{before}\n{custom_instructions.strip()}\n{after}"
        else:
            return f"{section_prompt.rstrip()}\n{custom_instructions.strip()}\n"
    else:
        return section_prompt


def build_tools_section(tools):
    """
    Build the TOOLS section as a string from a list of Tool objects.
    """
    if not tools:
        return ""
    tools_section = ""
    for tool in tools:
        tools_section += f"## {tool.name}\n"
        tools_section += f"{tool.description}\n"
        tools_section += "Parameters:\n"
        for name, param in tool.parameters.items():
            required = "(required)" if param.get("required", False) else ""
            tools_section += f"- {name}: {param.get('description', '')} {required}\n"
        tools_section += "Usage:\n"
        tools_section += f"<{tool.name}>\n"
        for name in tool.parameters:
            tools_section += f"<{name}>{name} here</{name}>\n"
        tools_section += f"</{tool.name}>\n\n"
    return tools_section


def build_system_prompt(
    # Description
    description=None,
    # Tool calling instructions
    add_tool_instructions=True,
    # Tools
    tools=None,
    # Rules
    custom_rules=None,
    add_default_rules=True,
    # Objective
    custom_objective=None,
    add_default_objective=True,
    # Additional context
    additional_context=None,
    # Custom instructions (not rules/objective)
    custom_instructions=None,
    # Think instructions
    add_think_instructions: bool = False,
    # Final output instructions
    add_final_output_instructions: bool = False,
):
    """
    Build the full system prompt from all config values.
    """
    # DESCRIPTION section
    description_section = description if description is not None else description_prompt

    # TOOL USE section
    tool_calling_section = tool_calling_prompt if add_tool_instructions else ""

    # TOOLS section
    tools_section = build_tools_section(tools) if add_tool_instructions else ""

    # ADDITIONAL CONTEXT section
    additional_context_section = ""
    if additional_context is not None:
        if isinstance(additional_context, list):
            context_str = "\n".join(additional_context)
        else:
            context_str = additional_context
        additional_context_section = additional_context_prompt.replace(
            "{additional_context}", context_str
        )

    # RULES section (merge default and custom)
    rules_section = ""
    if add_default_rules:
        rules_section = insert_custom_instructions(
            rules_prompt,
            "\n".join(custom_rules) if isinstance(custom_rules, list) else custom_rules,
        )
    elif custom_rules is not None:
        rules_section = (
            "\n".join(custom_rules) if isinstance(custom_rules, list) else custom_rules
        )

    # OBJECTIVE section (merge default and custom)
    objective_section = ""
    if add_default_objective:
        objective_section = insert_custom_instructions(
            objective_prompt,
            (
                "\n".join(custom_objective)
                if isinstance(custom_objective, list)
                else custom_objective
            ),
        )
    elif custom_objective is not None:
        objective_section = (
            "\n".join(custom_objective)
            if isinstance(custom_objective, list)
            else custom_objective
        )

    # THINKING PROCESS section
    think_section = think_prompt if add_think_instructions else ""

    # FINAL OUTPUT INSTRUCTIONS section
    final_output_section = final_output_prompt if add_final_output_instructions else ""

    # Compose the full prompt in the correct order, without extra section headers
    sections = [
        description_section,
        tool_calling_section,
        tools_section,
        think_section,
        rules_section,
        objective_section,
        additional_context_section,
        final_output_section,
    ]
    full_prompt = ""
    for content in sections:
        if content:
            # Ensure each section is separated by a single newline
            if not full_prompt.endswith("\n") and full_prompt:
                full_prompt += "\n"
            full_prompt += content.strip() + "\n\n"

    # Add any extra custom instructions (not rules/objective) at the end
    if custom_instructions is not None:
        if isinstance(custom_instructions, list):
            instructions_str = "\n".join(custom_instructions)
        else:
            instructions_str = custom_instructions
        full_prompt += f"{instructions_str}\n"

    return full_prompt.strip() + "\n"
