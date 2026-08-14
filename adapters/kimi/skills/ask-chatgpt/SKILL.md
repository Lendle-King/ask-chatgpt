---
name: ask-chatgpt
description: 向 ChatGPT 网页版（GPT-5.6 Sol，High 思考，可选联网搜索）提问并取回答案。用于复杂困难问题、架构/实验设计审查、需要第二意见的决策、多次尝试未果的难题。
---

# ask-chatgpt

通过本机已登录的 ChatGPT 网页版提问，拿回 GPT-5.6 Sol（High 思考强度）的回答。底层是 CDP 驱动的真实浏览器会话，不是 API。

## 命令

```sh
python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" ask "<问题>" [--search] [--timeout 秒]
```

- 问题作为单个参数传入（引号包裹，可含换行）。
- `--search`：开启 ChatGPT 的 Web 搜索（联网核实类问题加上）。
- `--timeout`：整体超时秒数。建议：简单问题 120；一般技术问题 300；长架构审查 420。
- 固定使用 GPT-5.6 Sol + High 思考强度，无需也无法在调用时更改。

## 输出契约

stdout 输出一行 JSON（stderr 是过程日志，无需解析）：

```json
{"success": true, "answer": "...", "model": "GPT-5.6 Sol", "effort": "high", "search": false, "stalled": false, "elapsed_s": 74.6}
```

- `answer`：回答全文（Markdown 文本）。
- `stalled: true`：流式响应尾部停滞，CLI 已主动停止并提取了已渲染内容；答案末尾可能被截断，重要场景可据此判断是否需要重问。
- 失败时输出 `{"success": false, "error": "..."}` 且退出码为 1：把 `error` 内容如实报告给用户。若带 `partial` 字段，说明有部分已生成文本，可一并参考。

## 状态检查

```sh
python3 "$HOME/.hermes/scripts/chatgpt_web_cli.py" status
```

返回 `logged_in`、`composer` 等状态。`logged_in=false` 或连接失败 = 浏览器服务未运行，告知用户，不要自行修复浏览器。

## 规则与陷阱

- 问题必须自包含、无秘密：不含凭证、Cookie、Token、私有值、不可外发的代码或数据。
- 长思考（High）期间 1–4 分钟没有任何文本输出是正常现象，CLI 内部已正确处理，不要提前 kill。
- 共享单标签页：同一时间只允许一个调用运行，禁止并发，也不要与其他 agent 的调用叠加。
- 单次回答约 15–90 秒（带搜索/长思考更久），脚本本身可能运行数分钟——给 Bash 调用设置足够的外层超时。
- 失败（success=false / 退出码 1）：不要在没有新证据时盲目重试；先 `status` 检查，再决定重试或报告用户。不要因此阻塞当前任务。
- 首次调用失败或未配置完成（连不上 Chrome / logged_in=false）：提醒用户查看项目 README（https://github.com/Lendle-King/ask-chatgpt#readme）——含 GUI 直接登录与无 GUI cookie 导入两种路径。
