---
title: "Image Search"
description: 'DeerFlow 有三个 image search provider：DuckDuckGo（默认，无 key）、Brave Image（BRAVE_API_KEY，返回尺寸与来源）、InfoQuest（字节内部）。所有 provider 返回的图片 URL 都过 url_safety 过滤，view_image 是唯一让模型真正「看到」图片的通道。'
topics: [tools, community, external-integration]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Image Search

三个 image search provider，共用 `@tool("image_search", parse_docstring=True)` 这一个工具名——所以**同时只能启用一个**（`get_available_tools()` 按名去重）。

| Provider | 文件 | 认证 | Async | 特有字段 |
|----------|------|------|-------|---------|
| **DuckDuckGo**（默认） | `community/image_search/tools.py:77-78` | 无 | **是** | `size`/`color`/`type_image`/`layout`/`license_image` 五档过滤 |
| **Brave Image** 🆕 | `community/brave/tools.py:194-195` | `BRAVE_API_KEY` | 否 | `width`/`height`/`source` |
| **InfoQuest** | `community/infoquest/tools.py:123-124` | `INFOQUEST_API_KEY` | **是** | 无（`query` 是唯一参数） |

## DuckDuckGo Image Search（默认）

- **文件：** `community/image_search/tools.py:77-78`
- **签名：**
  ```python
  @tool("image_search", parse_docstring=True)
  async def image_search_tool(
      query: str,
      max_results: int = DEFAULT_MAX_RESULTS,
      size: str | None = None,          # Small/Medium/Large/Wallpaper
      color: str | None = None,         # color/Monochrome/Red/...
      type_image: str | None = None,    # photo/clipart/gif/transparent/line
      layout: str | None = None,        # Square/Tall/Wide
      license_image: str | None = None, # any/Public/Share/ShareCommercially/...
  ) -> str:
  ```
- **认证：** 无（使用 `ddgs` 库，与 DDG web search 共享依赖）
- **返回格式：**
  ```json
  {
    "query": "...",
    "total_results": N,
    "results": [{"title": "...", "image_url": "...", "thumbnail_url": "..."}],
    "usage_hint": "You can use view_image tool to view the image in detail..."
  }
  ```
- **配置：** `config.tool_config("image_search").model_extra["max_results"]`（经共享 `coerce_max_results(..., provider="DDG image search", ...)`）
- **注意：** `image_url` 字段实际填充的是 DDG 的 `image` 字段（DDG 侧本身就是缩略/中等尺寸，不是原图 URL）
- **2.2.0：阻塞 I/O 全在一个 worker 里**：`config` 解析 + `ddgs` 调用一起包进 `search_with_config()` 再 `await asyncio.to_thread(...)`——注释理由「Both config loading and DDGS perform blocking I/O. Keep the entire search setup in one worker so neither can stall the agent event loop.」
- **2.2.0：URL 安全过滤**：`image_url` / `thumbnail_url` / `source_url` 逐个过 `safe_public_result_url()`；两个 URL 都被过滤掉的行直接**丢弃**，全部丢完时返回 `{"error": "No safe image URLs found"}`（而不是「No images found」——这两个错误的含义不同）

### 可选过滤参数

| 参数 | 可选值 | 作用 |
|------|--------|------|
| `size` | Small, Medium, Large, Wallpaper | 图片尺寸过滤 |
| `type_image` | photo, clipart, gif, transparent, line | 图片类型 |
| `layout` | Square, Tall, Wide | 图片宽高比 |

⚠️ **旧版描述有误**：`color` 与 `license_image` 自 2.2.0 起**已在 tool signature 中显式暴露**（见上方签名），不再靠 `kwargs` 透传；两者也都带完整 docstring 说明（例如「`"color"` 表示全彩，不是元参数」「要被再分发的参考图应传 `license_image`」）。

### Brave Image Search 🆕

- **文件：** `community/brave/tools.py:194-195`（`def image_search_tool(query, max_results=5)`）
- **认证：** `BRAVE_API_KEY`（`_get_api_key("image_search")`，缺失 → `_missing_key_error`）
- **端点：** Brave Image Search API，`count` 由 `_coerce_max_results(max_results, max_allowed=_BRAVE_IMAGE_MAX_COUNT)` 归一并 clamp（**cap 200**）；额外配置 `country`/`search_lang`/`safesearch`/`spellcheck` 原样透传给 Brave
- **返回格式：** 比 DDG 多两维信息——`{title, image_url, thumbnail_url, source_url, source, width, height}`，`count` 条即停
- **尺寸归属的巧思**（`:253-270`）：`image_url` 可能被 URL 安全过滤掉而回落到 `thumbnail`，此时 `width`/`height` 必须描述**真正返回的那个 URL**——所以代码记住每个 URL 来自 `properties` 还是 `thumbnail` dict，按「最终选了哪个」取尺寸，而不是盲目用 `properties` 的宽高
- **注意：** 这是**同步** provider（`httpx` 阻塞调用），与 DDG/InfoQuest 的 async 形态不同

## InfoQuest Image Search

- **文件：** `community/infoquest/tools.py:123-124`（`async def image_search_tool(query: str)`）
- **签名：** **只有 `query`**，不像 DDG 那样有过滤参数
- **认证：** `INFOQUEST_API_KEY`
- **实现：** `client = await asyncio.to_thread(_get_infoquest_client)` 后 `await client.image_search(query)`——client 构造（含配置解析）在 worker 线程
- **用途：** 字节跳动内部场景，中文图片搜索优化

## 与 Vision Model 的对接

Image search 产出的 URL 需要通过 `view_image` tool 才能被 model "看到"：

```
Agent 调用 image_search("cats")
  → 返回 JSON [{title, image_url, thumbnail_url}]
  → Agent 选择感兴趣的图片
  → Agent 调用 view_image(image_url)
    → 路径校验（限定 /mnt/user-data/{workspace,uploads,outputs}）
    → 如果 URL 是外部链接 → download 到 uploads/ → 再 view
    → base64 编码 → 存入 ThreadState.viewed_images
  → ViewImageMiddleware 在下一轮 model 调用前注入图片
  → Vision-capable model 看到图片
```

重要约束：`view_image` tool 只能读取三个虚拟路径下的文件。**2.2.0 起外部 URL 的下载是托管的、带预算的**（`backend/packages/harness/deerflow/sandbox/download.py`：图片上限 `MAX_IMAGE_BYTES = 20 MiB`，一般下载 `DEFAULT_DOWNLOAD_LIMIT = 100 MiB`），不再依赖「先自己 fetch 到 uploads/」。同时图片 URL 在进入这条链路之前已被 image search provider 用 `safe_public_result_url()` 过滤过一轮（无 DNS）；下载器在连接时还要再做一次解析地址检查——**两层都不是可选的**。

## 底层实现

使用 `ddgs.DDGS().images()` 调用 DuckDuckGo 的 image search API（非官方，HTML scraping）：

```python
# community/image_search/tools.py:73
results = ddgs.images(query, **kwargs)
```

结果字段映射（`community/image_search/tools.py:142-152`）：

- `row["title"]` → `title`（非 `str` 则空串）
- `row["image"]` → `image_url`（DDG 侧的中等尺寸图，不是原图）
- `row["thumbnail"]` → `thumbnail_url`
- `row["url"]` → `source_url` 🆕（结果页）

三者都先过 `safe_public_result_url()`；`image_url` 与 `thumbnail_url` **同时**为空的行被 `continue` 掉。
