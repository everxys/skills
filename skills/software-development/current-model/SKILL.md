---
name: current-model
description: Use when asked what model you or a CLI are running.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [model, provider, config, identity]
    related_skills: [windows-software-inventory]
---

# current-model — 秒答「你是什么模型」

## When to Use

用户问「你是什么模型 / 当前模型是什么 / 用的哪个 provider」，或需要查其他 agent CLI（Codex、Claude Code、Gemini CLI、DeepSeek Harness…）当前跑的模型时。回答不超过一句话。

## 规则

1. **本会话最权威的来源是系统提示的 `Model:` / `Provider:` 行**（模型可能在会话中被切换，config.yaml 未必同步）。它存在就直接用，**不要为回答这一句去跑任何工具**。
2. 只有在需要交叉核对、或用户问的是**其他 agent CLI**（Codex / Claude Code / Gemini CLI / DeepSeek Harness …）时才跑脚本。
3. 回答保持一句话，不要展开工具链、不要列举能力清单。

## 快查命令（0.1 秒，纯文件读）

```bash
which-model            # Hermes: model / provider / base_url / effort
which-model --json     # 机器可读
which-model --agents   # 额外列出所有 agent 的当前模型（magpie ls，~0.7s）
```

实现在 `~/.local/bin/which-model.py`（bash 走 `which-model`，cmd/PowerShell 走 `which-model.cmd`）。数据源：`%LOCALAPPDATA%\hermes\config.yaml` 的 `model.default` / `model.provider` / `model.base_url`。

## 答复格式

一句话即可，例如：
`DeepSeek V4.1 Flash Fast（deepseek/deepseek-v4.1-flash-fast），provider commandcode，effort medium。`

## 不要做的事

- 不要为了这个问题读整个 config.yaml、grep 全库、或 web_search。
- 不要用 `magpie ls` 回答本会话模型（它只反映 config，且慢 7 倍）。
- 不要把 provider 名（commandcode / openrouter）当成模型名报给用户。
