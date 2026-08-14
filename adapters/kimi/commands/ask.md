---
description: 向 ChatGPT Web（GPT-5.6 Sol/High）提问并返回回答；如需联网搜索在问题中说明
---

用 Bash 运行以下命令向 ChatGPT 网页版提问（GPT-5.6 Sol，High 思考强度）：

```sh
python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" ask "$ARGUMENTS" --timeout 300
```

要求：

- 把 `$ARGUMENTS` 整体作为问题传入；若用户要求联网核实，追加 `--search`。
- 问题中不得包含任何凭证、Cookie、Token 或私有值。
- 解析 stdout 的一行 JSON：用 `answer` 字段回答用户；若 `success=false`，如实报告 `error` 并先运行 `python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" status` 排查，不要无新证据盲目重试。
- 首次调用失败或未配置完成时，提醒用户查看项目 README（https://github.com/Lendle-King/ask-chatgpt#readme）。
- 外层 Bash 超时要大于 `--timeout`（建议至少 330 秒）。
