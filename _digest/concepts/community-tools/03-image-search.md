---
title: "Image Search"
description: "DeerFlow 有两个 image search provider，都使用 DuckDuckGo 作为后端。"
topics: [tools, community, external-integration]
---

# Image Search

DeerFlow 有两个 image search provider，都使用 DuckDuckGo 作为后端。

## DuckDuckGo Image Search（默认）

- **文件：** `community/image_search/tools.py:77`
- **签名：**
  ```python
  @tool("image_search", parse_docstring=True)
  def image_search_tool(
      query: str,
      max_results: int = 5,
      size: str | None = None,       # Small/Medium/Large/Wallpaper
      type_image: str | None = None,  # photo/clipart/gif/transparent/line
      layout: str | None = None,      # Square/Tall/Wide
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
- **配置：** `config.tool_config("image_search").model_extra["max_results"]`
- **注意：** `image_url` 字段实际填充的是 thumbnail URL（不是原图 URL）

### 可选过滤参数

| 参数 | 可选值 | 作用 |
|------|--------|------|
| `size` | Small, Medium, Large, Wallpaper | 图片尺寸过滤 |
| `type_image` | photo, clipart, gif, transparent, line | 图片类型 |
| `layout` | Square, Tall, Wide | 图片宽高比 |

还有 `color` 和 `license_image` 参数（代码中定义但未在 tool signature 中暴露，通过 `kwargs` 传递）。

## InfoQuest Image Search

- **文件：** `community/infoquest/tools.py:78`
- **签名：** 与 DDG image search 相同接口
- **认证：** `INFOQUEST_API_KEY`
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

重要约束：`view_image` tool 只能读取三个虚拟路径下的文件——不能直接传入外部 URL。要实现 "搜索→查看" 的完整链路，image search 返回的 URL 需要先被下载到 uploads/ 目录。

## 底层实现

使用 `ddgs.DDGS().images()` 调用 DuckDuckGo 的 image search API（非官方，HTML scraping）：

```python
# tools.py:43-49
from ddgs import DDGS
ddgs = DDGS()
results = ddgs.images(query, max_results=max_results, size=size, ...)
```

结果字段映射：
- `result["title"]` → `title`
- `result["image"]` → `image_url`（注意：这是 DDG 的 thumbnail，不是原图）
- `result["thumbnail"]` → `thumbnail_url`
