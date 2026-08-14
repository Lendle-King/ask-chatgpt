# Ask ChatGPT（ChatGPT Web 问答）

你可以通过本地 CLI 向 ChatGPT 网页版（GPT-5.6 Sol，思考强度 High，可选联网搜索）提问并拿到回答。适用场景：复杂困难的技术问题、架构或实验设计审查、需要第二意见的歧义决策、自己多次尝试仍失败的难题。

调用方式（用 Bash 运行，完整契约见 ask-chatgpt 技能）：

```sh
python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" ask "<问题>" --timeout 300
```

规则：

- 问题必须自包含且无秘密：不得包含任何凭证、Cookie、Token、私有值或不可外发的代码/数据。
- 需要联网核实时加 `--search`。
- 超时按复杂度设置：简单问题 120s；长架构/审查类问题 300–420s（High 思考可能 2–4 分钟，期间没有文本输出属正常）。
- 解析 stdout 的一行 JSON：`answer` 字段即回答；`success=false` 时向用户报告 `error` 内容。不要在没有新证据时盲目重复调用，也不要因此阻塞当前任务。
- 该服务是共享单浏览器标签页：同一时间只运行一个调用，禁止并发。
- 失败排查先运行 `python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" status`；若 `logged_in=false` 或无法连接 Chrome，说明浏览器服务未运行，告知用户处理，不要自行修复浏览器。
- 首次调用失败或确认未配置完成时，提醒用户查看项目 README（https://github.com/Lendle-King/ask-chatgpt#readme），里面有 GUI/无 GUI 两种登录方式和完整排障。
