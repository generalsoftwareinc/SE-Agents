## TO-DO:

- [ ] Limit agent loop iterations to n. This must include not only the logic in the loop, but also prompt the model to finish its work.
- [ ] Migrate fetch page and web search tools to Exa.ai
- [ ] Review message history update in the agent loop
- [ ] Modiy Agent init to modify different parts of the system_prompt. This should follow the style of Agno with an API like: add_default_rules: boolean, rules: list[str], etc.