---
title: "如何添加新的 Tool Provider"
description: "一步一步指南：创建一个新的社区工具 provider，从目录结构到 config.yaml 注册，含认证模式。"
topics: [tools, community, integration, howto]
---

# 如何添加新的 Tool Provider

## 目录结构

```
deerflow/community/{provider_name}/
├── __init__.py     # 导出 tool 函数
└── tools.py        # @tool 装饰的函数
```

`__init__.py` 是可选的，但推荐——让 `resolve_variable()` 可以直接 import 你的模块。

## 步骤

### 1. 创建 tool 函数

```python
# deerflow/community/my_provider/tools.py
from langchain.tools import tool

@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web for the given query.

    Args:
        query: The search query string.

    Returns:
        JSON string with search results.
    """
    # 你的实现
    results = my_api.search(query)
    return json.dumps({"query": query, "results": results})
```

**关键规则**：
- `@tool` 的 name（`"web_search"`）会被用于去重——如果另一个 provider 也注册了 `web_search`，`get_available_tools()` 按名字去重，先匹配的生效
- 返回字符串（LLM 看到 ToolMessage content），可以是 JSON 或纯文本
- 函数签名中的参数就是 LLM function-calling schema

### 2. 读取 API key

两种模式，参考现有 provider 任选其一：

**模式 A：从 config.yaml 读（推荐）**
```python
from deerflow.config import get_app_config

@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    cfg = get_app_config().tool_config("web_search")
    api_key = cfg.model_extra.get("api_key")  # ToolConfig.extra="allow" 透传任意字段
    ...
```

**模式 B：从环境变量读**
```python
import os
api_key = os.getenv("MY_PROVIDER_API_KEY")
```

### 3. 注册到 config.yaml

```yaml
tools:
  # 注释掉旧的 provider
  # - name: web_search
  #   use: deerflow.community.tavily.tools:web_search_tool

  # 启用新的 provider
  - name: web_search
    group: web
    use: deerflow.community.my_provider.tools:web_search_tool
    api_key: $MY_PROVIDER_API_KEY  # ToolConfig.extra="allow" 透传
    max_results: 10                # 任意额外字段
```

**注意**：一次只能有一个 `web_search` 生效（按名字去重）。注释掉旧的，取消注释新的。

### 4. 验证

```bash
# 启动后检查 tool 是否注册
curl http://localhost:8001/api/models  # 确认 agent 可用

# 用 DeerFlowClient 测试
python -c "
from deerflow.client import DeerFlowClient
c = DeerFlowClient()
print(c.chat('用 web_search 搜索 Python 3.13 新特性'))
"
```

## 返回格式

虽然格式自由，但大多数 provider 返回 `{query, total_results, results: [{title, url, snippet}]}`。保持与其他 provider 一致有助于 LLM 在切换 provider 时行为可预测。

## 测试

```python
# tests/community/test_my_provider.py
from deerflow.community.my_provider.tools import web_search_tool

def test_web_search_returns_results():
    result = web_search_tool.invoke({"query": "test"})
    assert len(result) > 0

def test_empty_query_handled():
    result = web_search_tool.invoke({"query": ""})
    assert result is not None  # 不应崩溃
```

## 现有 Provider 参考

| Provider | 文件 | 认证 | 返回格式 |
|----------|------|------|---------|
| Tavily | `community/tavily/tools.py` | env var | `{query, results: [...]}` |
| DuckDuckGo | `community/ddg_search/tools.py` | 无 | `{query, total_results, results: [...]}` |
| Serper | `community/serper/tools.py` | env var | `{query, total_results, results: [...]}` |
| Brave | `community/brave/tools.py` | env var | `{query, results: [...]}` |
| SearXNG | `community/searxng/tools.py` | config | `{query, results: [...]}` |

源码路径：`deerflow/community/{provider}/tools.py`
