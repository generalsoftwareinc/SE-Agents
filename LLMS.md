# LLM findings and usage recommendations

## Main Findings

- grok-3-mini: Very fast, cheap and reliable. It's too polite and and the response style is very verbose. Is a reasoning model so there is an initial latency hit, but its small due to the speed of the model. Best small model so far, only issue is response style. 
- grok-3: Fast, reliable, very expensive. Its good using our tool format. Responses are verbose but personality and style is ok. Not a reasoning model so there is no initial latency hit.
- minimax-m1: Very slow, good pricing (cheaper than Gemini Flash and GPT-4.1-mini), open-source, very reliable. It's compatible with our tool format. Responses are a bit verbose. Is a reasoning model and latency hit is very noticeable.
- deepseek-r1(latest): Very slow, good pricing, open-source. It has minor issues with the tool call format. It's very smart. Speed can be improved by sacrificing pricing. Latency hit due to reasoning.
- gpt-4.1-mini: Fast, good pricing, reliable. It's good using our tool format. No latency hit. It asks for authorization on every tool call and refuses to use multiple tools in sequence autonomously.
- gpt-4.1: Fast, high-end pricing, reliable. It's good using our tool format. No latency hit. It asks for authorization on every tool call and refuses to use multiple tools in sequence autonomously.
- qwen3-32b: Medium speed, good pricing even in nitro endpoint. It's not good at using our tool format. Latency hit due to reasoning. Doesn't show strong agentic behavior (does not call multiple tools in sequence autonomously and likes to finish tasks early).
- qwen3-235b-a22b: Slow, good pricing, open-source. Presents minor inconsistencies when using our tool calling format. Very big latency hit due to reasoning. Very similar to deepseek-r1(latest) but slower and worse agentic behavior.
- llama-3.3-nemotron-super-49b-v1: Fast, good pricing, open-source. Bad with our tool format. Very eager agentic behavior but needs specific instructions and optimization. No latency hit. Limited intelligence compared to similar price competitors.
- magistral-small-2506: Fast, average pricing. Bad with out tool calling format. Weird formatting issues in the responses. Latency hit due to reasoning.
- mistral-small-3.2: Fast, good princing. Bad with our tool format. Weird formatting issues in the responses. No latency hit. Promising agentic behavior for the price.
- gemini-2.5-flash: Very Fast, good pricing, reliable. Compatible with our tool calling format. No latency hit. Agentic behavior is not the most advanced, but is realiable.
- gemini-2.5-pro: Fast, high-end pricing, reliable. Compatible with our tool calling format. Latency hit due to reasoning, but small thanks to the speed. Very smart model and reliable agentic behavior.
- o4-mini(medium): Medium speed, middle range pricing, reliable. It's good using our tool format. Latency hit due to reasoning. Agentic behavior is poor as it requires approval and nogging to call multiple tools in sequence, similar to gpt-4.1.

## Usage Recommendations

Based on the findings, here are the recommendations for model usage:

### **Tier 1: Top Performers**

These models offer the best balance of speed, intelligence, and agentic capabilities for complex tasks.

- **gemini-2.5-pro**: The best all-around model. It's fast, highly intelligent, and exhibits reliable agentic behavior with minimal latency hit. The go-to choice for demanding, multi-step tasks.
- **grok-3**: A strong alternative to `gemini-2.5-pro`. It's fast and reliable with tools, but comes at a very high price point. Its verbose style is more manageable than its smaller counterpart.

### **Tier 2: Fast & Reliable**

These models are ideal for tasks where speed and cost-effectiveness are priorities, without sacrificing reliability.

- **gemini-2.5-flash**: The top choice for this category. Very fast, affordable, and reliable with our tool format. A perfect default model for general-purpose tasks.
- **grok-3-mini**: Extremely fast and cheap, but its excessive politeness and verbosity can be a significant drawback. Best used when raw speed and cost is the absolute priority and response style is not a concern.

### **Tier 3: Budget-Friendly Open Source**

For scenarios where using open-source models is a priority and performance can be compromised.

- **deepseek-r1(latest)**: The smartest open-source option. It's slow and has minor tool-calling issues, but its intelligence is top-tier. A good choice for offline, complex problem-solving.
- **minimax-m1**: A very reliable and cost-effective open-source model. Its main drawback is the very slow speed and noticeable latency hit.

### **Models to Use with Caution or Avoid**

- **GPT Models (4.1 and 4.1-mini)**: While fast and reliable, their refusal to perform sequential tool calls without explicit authorization on every step makes them unsuitable for autonomous agentic tasks.
- **Qwen Models (qwen3-32b, qwen3-235b-a22b)**: Poor tool format compatibility and weak agentic behavior.
- **Other Models (llama-3.3, magistral-small, mistral-small)**: Suffer from significant issues with tool calling, formatting, or limited intelligence, making them unreliable for our use case.
- **o4-mini(medium)**: Poor agentic behavior requiring constant intervention, similar to GPT models.
