# SE Agents: Autonomous LLM Agent Framework

`se-agents` provides a lightweight Python framework for building autonomous agents powered by large language models (LLMs). It simplifies integrating external tools, managing conversation history, and handling asynchronous operations, allowing developers to focus on agent capabilities.

## Key Features

*   **Pluggable Tools**: Easily integrate external tools like web search (Exa, DuckDuckGo), page crawling (Exa, Firecrawl), or custom functions. Includes built-in tools for thinking (`ThinkTool`) and signaling final output (`FinalOutput`).
*   **Streaming Responses**: Handles asynchronous streaming of LLM responses and tool events.
*   **Customizable System Prompts**: Fine-tune agent behavior through configurable descriptions, rules, objectives, and instructions.
*   **Context Management**: Automatically truncates conversation history to fit within token limits.
*   **Clear Event Model**: Uses `ResponseEvent` schema for structured communication between `Agent` and `Runner`.

## Installation & Requirements

```bash
pip install git+https://github.com/generalsoftwareinc/SE-Agents.git
```

**Requirements:**

*   Python >= 3.12
*   Dependencies:
    *   `duckduckgo-search>=7.5.2`
    *   `exa-py>=1.12.1`
    *   `firecrawl-py>=1.14.1`
    *   `openai>=1.66.3`
    *   `python-dotenv>=1.0.1`

## Quickstart

This minimal example shows how to initialize an agent and run a single query.

**Note:** This example assumes your environment variables (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `EXA_API_KEY`) are already set in your environment.

```python
import asyncio
import os

from se_agents.agent import Agent
from se_agents.runner import Runner
from se_agents.tools import ExaSearch # Import desired tools

async def run_query():
    # Read environment variables
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    exa_key = os.getenv("EXA_API_KEY") # Optional, for Exa tools

    if not api_key or not model:
        print("Error: OPENROUTER_API_KEY or OPENROUTER_MODEL not set.")
        return

    # Initialize agent with desired tools
    agent = Agent(
        api_key=api_key,
        model=model,
        tools=[ExaSearch(exa_key)] if exa_key else [] # Example: Use ExaSearch if key exists
    )
    runner = Runner(agent)

    print("Running query: What is the capital of France?")
    async for event in runner.run("What is the capital of France?"):
        if event.type == "response":
            print(event.content, end="", flush=True)
        # Handle other event types like 'tool_call', 'tool_response' as needed
    print("\nQuery finished.")

if __name__ == "__main__":
    asyncio.run(run_query())
```

## Example: Interactive CLI

This example demonstrates initializing an agent with Exa tools and running an interactive command-line loop (similar to `main.py`).

```python
import asyncio
import datetime
import os
from dotenv import load_dotenv

from se_agents.agent import Agent
from se_agents.runner import Runner
from se_agents.tools import ExaCrawl, ExaSearch

# Load environment variables from .env file
load_dotenv(override=True)

async def main():
    # Retrieve API keys and model info from environment variables
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    base_url = os.getenv("OPENROUTER_BASE_URL")
    exa_key = os.getenv("EXA_API_KEY")

    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        return
    if not exa_key:
        print("Warning: EXA_API_KEY not set, Exa tools will not function.")
        # Handle appropriately, e.g., use different tools or exit

    # Instantiate the agent
    agent = Agent(
        api_key=api_key,
        base_url=base_url,
        model=model,
        tools=[ExaSearch(exa_key), ExaCrawl(exa_key)] if exa_key else [], # Conditionally add tools
        additional_context=f"Current system time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        verbose=True, # Set to False for less console output
        # Example of custom rules (add_default_rules=False prevents default rules)
        # rules="1. Be extremely concise.",
        # add_default_rules=False,
    )

    # Initialize the runner
    runner = Runner(agent)
    print("🤖 Starting agent loop...")
    print("Type 'exit' to end the conversation\n")

    while True:
        user_input = input(f"\nUser: ")
        if user_input.lower() == "exit":
            break

        print(f"\nAssistant: ", end="")

        # Run the query and process events
        async for response in runner.run(user_input):
            if response.type == "response":
                # This will typically contain the final output when enforce_final=True,
                # or intermediate text otherwise.
                print(response.content, end="", flush=True)
            # Note: 'thinking' is now handled via ThinkTool, resulting in 'tool_call' and 'tool_response' events.
            elif response.type == "tool_call":
                # Includes calls to ThinkTool, FinalOutput, and others.
                print(f"\n\n\033[92m🟡 Tool Call:\n{response.content}\033[0m\n")
            elif response.type == "tool_response":
                print(f"\n\n\033[94m🟢 Tool Response:\n{response.content}\033[0m\n")
            elif response.type == "tool_error":
                print(f"\n\n\033[91m🔴 Tool Error:\n{response.content}\033[0m\n")

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

The framework relies on environment variables for API keys and model configuration. Create a `.env` file in your project root or set them directly in your environment:

| Variable            | Description                                  | Required | Default |
|---------------------|----------------------------------------------|----------|---------|
| `OPENROUTER_API_KEY`| API key for OpenRouter (or compatible API)   | Yes      | -       |
| `OPENROUTER_MODEL`  | LLM model identifier (e.g., `openai/gpt-4o`) | Yes      | -       |
| `OPENROUTER_BASE_URL`| (Optional) Custom API base URL             | No       | OpenAI default |
| `EXA_API_KEY`       | (Optional) API key for Exa AI tools        | No       | -       |
| `FIRECRAWL_API_KEY` | (Optional) API key for Firecrawl tools     | No       | -       |
| `add_think_instructions` | (Optional) Boolean to include THINKING PROCESS instructions in the system prompt. | No | `False` |
| `add_final_output_instructions` | (Optional) Boolean to include FINAL OUTPUT INSTRUCTIONS in the system prompt. | No | `False` |

## Core Concepts

*   **`Agent`**: The core component responsible for:
    *   Building the system prompt based on configuration (description, rules, tools, etc.).
    *   Interacting with the LLM API (currently OpenAI compatible).
    *   Parsing LLM responses for text and tool calls (XML format).
    *   Managing conversation history and context window truncation.
    *   Yielding `ResponseEvent` objects via the `run_stream` method.
*   **`Runner`**: Manages the interaction loop:
    *   Takes user input.
    *   Calls the `Agent.run_stream` method.
    *   Handles `tool_call` events by executing the corresponding tool via `Agent._execute_tool`.
    *   Feeds `tool_response` or `tool_error` back into the `Agent` for the next LLM turn.
    *   Yields `ResponseEvent` objects to the caller. Can optionally enforce the use of the `FinalOutput` tool via the `enforce_final` constructor argument.
*   **`ResponseEvent`**: A Pydantic model defining the structure of events yielded by the `Runner`:
    *   `type`: "response", "tool_call", "tool_response", "tool_error" (Note: "thinking" is handled as a standard tool call/response).
    *   `content`: The associated text or XML payload.
*   **`Tool`**: Base class for all tools. Subclasses implement specific functionalities (e.g., web search, page crawl, thinking, final output) and define their `name`, `description`, and `parameters`.

## Built-in Tools

The framework includes several pre-built tools:

*   **`ExaSearch`**: Performs web searches using the Exa AI API.
    *   *Parameters*: `query` (required), `include_domains`, `exclude_domains`, `start_published_date`, `end_published_date`.
*   **`ExaCrawl`**: Fetches and extracts text content from a specific URL using the Exa AI API.
    *   *Parameters*: `url` (required).
*   **`ExaSearchContent`**: Performs a web search and returns the content of the results using the Exa AI API.
    *   *Parameters*: Same as `ExaSearch`.
*   **`DuckDuckGoSearch`**: Performs web searches using the DuckDuckGo Search API.
    *   *Parameters*: `query` (required).
*   **`FireCrawlFetchPage`**: Fetches and extracts Markdown content from a specific URL using the Firecrawl API. Handles large content by returning truncated versions.
    *   *Parameters*: `url` (required).
*   **`MockNumberTool` / `MockIntTool`**: Simple tools for testing parameter handling (float/integer).
    *   *Parameters*: `value` (required).
*   **`ThinkTool`**: Allows the agent to perform internal reasoning steps. The Runner intercepts this tool call.
    *   *Parameters*: `thought` (required).
*   **`FinalOutput`**: Signals the end of the agent's response cycle for a given input. Used especially when `enforce_final` is enabled in the `Runner`.
    *   *Parameters*: `result` (required).

## Advanced Usage

*   **Customizing System Prompts**: The `Agent` constructor accepts parameters like `description`, `rules`, `objective`, `instructions`, and `additional_context` to modify the default system prompt. Flags like `add_default_rules=False` allow complete replacement of sections. You can also include specific instructions for thinking steps (`add_think_instructions=True`) and the final output process (`add_final_output_instructions=True`).
*   **Verbose Mode**: Setting `verbose=True` when creating an `Agent` instance prints the constructed system prompt and context window management details to the console, aiding in debugging prompt logic.
*   **Adding Custom Tools**: Create a new class inheriting from `se_agents.tools.Tool`, define `name`, `description`, `parameters`, and implement the `execute` method. Pass an instance of your custom tool to the `tools` list during `Agent` initialization.

## Testing & Examples

*   The `main.py` file serves as a primary example of usage.
*   `split_string_test.py` contains a small utility test related to token splitting.

## Development & Contributing

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_GITHUB_USERNAME/se-agents.git
    cd se-agents
    ```
2.  **Set up the development environment using uv:**
    ```bash
    # Install uv if you haven't already: https://github.com/astral-sh/uv
    # Create a virtual environment
    uv venv
    ```
3.  **Activate the virtual environment:**
    ```bash
    source .venv/bin/activate
    # Or on Windows: .venv\Scripts\activate
    ```
4.  **Sync dependencies:**
    ```bash
    # Install dependencies specified in pyproject.toml and locked in uv.lock
    uv sync --dev # Installs base and development dependencies
    # Or install only base dependencies:
    # uv sync
    ```

**Contributions are welcome!** Please follow these guidelines:

*   Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
*   Open an issue to discuss significant changes before submitting a pull request.
*   Ensure tests pass before submitting a PR.

## Roadmap

Based on initial TODOs:

- [ ] Limit agent loop iterations to a configurable number `n`. This requires logic in the `Runner` and potentially prompting the model to conclude its task within the limit.
- [x] Implement final-output tool to allow the agent to close the loop. Include 'enforce final-output tool' option in the `Runner` constructor, which will prompt the model to conclude the task using the final-output tool. This will change current behavior of the 'response' event. Instead of all non-tool responses being yielded as events, only the final response will be yielded. If no final-output tool is found, the Runner will re run the Agent, prompting the model to conclude the task using the final-output tool.
- [x] Refactor block \<thinking> and event handling as a tool (`ThinkTool`), following the pattern described by the [Anthropic documentation](https://www.anthropic.com/engineering/claude-think-tool).
- [x] Remove the <tool_call> block parsing from the Agent, instead parse the tool call xml using the <tool_name> as top level tag. This required changes to the `Agent` and its prompts.
- [x] Yield chunks of the <tool_call> block as they are streamed, instead of yielding the whole block at once when it detects the end of the block. This would be useful for streaming thinking and final-output instead of waiting for the whole block to be parsed, improving the user experience. `Agent` class should yield all chunks of the <tool_call> block as they are streamed, but the `Runner` should only yield to clients the chunks corresponding to `ThinkTool` and `FinalOutput` calls, all other calls should be yielded as a whole after the whole block is parsed.
- [ ] Migrate tool call ResponseEvent to a JSON based schema, instead of returning the content of the tool_call as a str containing XML, return a valid python dict with the function parameters. This can be achieved by creating a child class ToolCallResponseEvent that extends ResponseEvent.
- [ ] Create a way to differentiate between the streaming response of tools and the llm output. This would allow the `Runner` to yield these tool responses even when enforce_final is enabled, while silencing the llm response.


## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Authors & Acknowledgments

*   Vicente Garofalo Jerez / VicentGJ
*   Acknowledgments to libraries used (OpenAI, Exa, etc.)
