---



title: "托管模型路由（Managed Models）"
description: '管理员在 Web 上建的模型 profile 怎么变成一次真实的 LLM 调用？provider 路由为什么必须留在服务端、不能由客户端或模型 ID 推断？密钥、revision、probe 的边界在哪？'
topics: [models, llm, config, gateway, security]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 托管模型路由（Managed Models）

> 同步基线：**v2.2.0**（`58fc5bd5b`）。行号为 v2.2.0 实测（`grep -n` 核对）。

管理员在 Web 上建的模型 profile 怎么变成一次真实的 LLM 调用？provider 路由为什么必须留在服务端、不能由客户端或模型 ID 推断？密钥、revision、probe 的边界在哪？

**回答的核心问题**：`config.yaml` 之外的第二模型来源（加密 catalog）如何与 YAML 合并成一次有效快照、12 个 provider preset 的「服务端拥有路由」契约、精确 ID 的能力矩阵、`/api/managed-models` 四个端点的鉴权/状态码/失败策略、以及 probe 为什么与真实 chat 走同一条 factory 路径。

## 文件

| 文件 | 行数（实测） | 角色 |
|------|------|------|
| `packages/harness/deerflow/config/managed_model_providers.py` | 142 | provider 注册表 + 能力矩阵 + 旧端点契约（harness 层，无 FastAPI 依赖） |
| `packages/harness/deerflow/config/managed_models.py` | 249 | `ManagedModel` pydantic 模型、`ManagedModelStore`（Fernet 加密 catalog）、`merge_managed_models()` |
| `app/gateway/routers/managed_models.py` | 182 | `/api/managed-models` 四个端点、`RedactedModelRoute`、probe |
| `packages/harness/deerflow/config/app_config.py` | — | `get_app_config()`（`:839`）/ `reload_app_config()`（`:865`）末尾调用 `merge_managed_models` |

## 解决什么问题

1. **不写 YAML 也能加模型**：`config.yaml` 是 operator 的文件（Docker 生产下 `:ro`）。管理员需要在不改文件、不重启的情况下增删模型 —— 于是有一个**加密 catalog**（`runtime_home()/managed-models/catalog.enc` + 同目录 `key`），在 `get_app_config()` 出口处**合并**进有效配置。
2. **把「路由」从「表单」里剥出来**：客户端只提交 `provider` + `model` + `api_key`（+ 少量能力覆盖），**不能**提交 endpoint / adapter 类路径 / 协议 / 认证头。否则任何能调该 API 的人都能把服务端的 `api_key` 发到自己的服务器（SSRF + 凭据外泄）。`managed_model_providers.py` 的文件头把这条写成第一句：`# Server-owned routing for managed models; never infer a provider from its ID.`（`:1`）。
3. **为每个厂商准备正确的 wire 细节**：同一句 `thinking: {type: enabled}` 在 DeepSeek 走 `extra_body`、在 Anthropic 走顶层 `thinking`；MiniMax 需要 `temperature: 1.0` 且把 `max_completion_tokens` 归一成 `max_tokens`；Moonshot K3.1 反过来**拒绝**任何 thinking 开关和固定采样键。
4. **不编造能力**：未知模型 ID 不给 context window、不给 vision、不给 reasoning —— 见 `_capabilities()` 的 docstring（`managed_model_providers.py:80-85`）。

## 数据形状

### `ManagedModel`（`managed_models.py:37-135`）

| 字段 | 行 | 约束 |
|------|----|------|
| `name` | `:39` | `^(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,99})?$` —— **允许空串**，空 = 新建时自动分配 |
| `provider` | `:40` | 默认 `openai-compatible`；`valid_provider`（`:74-78`）直接调 `get_managed_model_provider()`，未知 provider 抛 `ValueError("Unknown model provider")` |
| `display_name` | `:41` | ≤100 字符；空则回退 `"{provider.display_name} · {model}"[:100]`（`:200`、`:131`） |
| `model` | `:42` | 1..200 字符；`valid_model_id`（`:80-85`）拒绝 C0/C1 控制字符 |
| `base_url` | `:43` | ≤2048；`valid_endpoint`（`:52-64`）只允许 http/https、无 userinfo、无 query、无 fragment、端口 ≠ 0，并 `rstrip("/")` |
| `api_key` | `:44` | `SecretStr`；`reject_mask`（`:87-94`）拒绝 `＊*•●` 掩码串和纯空白 |
| `enabled` | `:45` | 默认 `True`；关闭的条目在合并时被过滤（`:244`） |
| `supports_vision` | `:46` | `bool \| None`；`None` = 用能力矩阵 |
| `reasoning` | `:47` | `ReasoningCapabilities`（`model_config.py:106`，`extra="forbid"`）；非 `None` 时**覆盖**矩阵推导出的 legacy 字段（`:115-124`） |
| `context_window` / `max_tokens` | `:48-49` | `int \| None, gt=0`；`numeric_capabilities`（`:69-72`）在 coerce 前用 `reject_boolean` 拒绝布尔 |
| `revision` | `:50` | `uuid4().hex`，每次保存重算（`:208`） |

`ModelConfig` 本身是 `extra="allow"`，所以 `runtime_config()` 返回的 `ModelConfig` 会把 `base_url`/`api_base`/`when_thinking_enabled` 等都塞进 `model_extra`，再由 factory 反射传给 provider 构造函数。

`public()`（`:66-67`）：`model_dump(exclude={"api_key"})` + `has_api_key: bool` + `source: "managed"`。**密钥字段永不离开服务端**。

### `ManagedModelProvider`（`managed_model_providers.py:18-32`）

```python
@dataclass(frozen=True)
class ManagedModelProvider:
    id: str; display_name: str; endpoint: str | None
    adapter: str = "langchain_openai:ChatOpenAI"
    protocol: str = "openai-chat"
    endpoint_parameter: str = "base_url"
    auth_parameter: str = "api_key"
    defaults: dict[str, Any] = field(default_factory=dict)
    authentication: str = "bearer"
```

`public()`（`:30-32`）**只暴露 4 个键**：`id` / `display_name` / `requires_api_key` / `custom_endpoint`。adapter、protocol、endpoint_parameter、auth_parameter、defaults、authentication 全部留在服务端。`tests/test_managed_provider_presets.py:151` 用 `set(p) == {"id", "display_name", "requires_api_key", "custom_endpoint"}` 钉死这个集合。

## 12 个 preset（`managed_model_providers.py:35-48`）

| `id` | endpoint | adapter | endpoint 参数 | 特殊 |
|------|----------|---------|--------------|------|
| `openai` | `https://api.openai.com/v1` | `langchain_openai:ChatOpenAI` | `base_url` | 基线 |
| `anthropic` | `https://api.anthropic.com` | `langchain_anthropic:ChatAnthropic` | `base_url` | `defaults={"max_tokens": 4096}`、`authentication="x-api-key"`、`protocol="anthropic-messages"` |
| `deepseek` | `https://api.deepseek.com` | `deerflow.models.patched_deepseek:PatchedChatDeepSeek` | **`api_base`** | — |
| `qwen-cn` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `PatchedChatDeepSeek` | `api_base` | 用 DeepSeek 适配器保 wire/history 字段 |
| `doubao` | `https://ark.cn-beijing.volces.com/api/v3` | `PatchedChatDeepSeek` | `api_base` | — |
| `doubao-coding` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `PatchedChatDeepSeek` | `api_base` | Coding Plan 独立 endpoint |
| `moonshot-cn` | `https://api.moonshot.cn/v1` | `PatchedChatDeepSeek` | `api_base` | K3.1 特殊（见下） |
| `zhipu-cn` | `https://open.bigmodel.cn/api/paas/v4` | `PatchedChatDeepSeek` | `api_base` | — |
| `zai` | `https://api.z.ai/api/paas/v4` | `PatchedChatDeepSeek` | `api_base` | 国际站 |
| `minimax` | `https://api.minimax.io/v1` | `deerflow.models.patched_minimax:PatchedChatMiniMax` | `base_url` | `defaults={"temperature": 1.0}` |
| `minimax-cn` | `https://api.minimaxi.com/v1` | `PatchedChatMiniMax` | `base_url` | 同上 |
| `openai-compatible` | `None` | `langchain_openai:ChatOpenAI` | `base_url` | `endpoint is None` → 客户端**必须**给 `base_url` |

`_PROVIDER_BY_ID`（`:49`）是唯一索引；`get_managed_model_provider()`（`:52-56`）把 `KeyError` 转成 `ValueError("Unknown model provider")`，且用 `from None` 抑制链式调用栈（避免回显探测细节）。

## 能力矩阵：精确 ID、禁止子串推断

`_capabilities(provider, model)`（`:80-135`）的默认返回是**最保守**的：

```python
result = {"reasoning": {"thinking": "unsupported", "dialect": "none"}}
```

然后是一串 `if/elif`，每条都要求 **provider 与 model ID 精确相等（或 `in` 一个写死的 frozenset）**：

| provider | 精确 model ID | vision | thinking / dialect | effort | 其它 |
|----------|--------------|--------|--------------------|--------|------|
| `openai` | `gpt-4o`/`gpt-4o-mini`/`gpt-4.1`/`gpt-4.1-mini`/`gpt-4.1-nano`（`:87`） | ✅ | 不支持 | — | — |
| `anthropic` | `claude-sonnet-4-20250514`/`claude-opus-4-20250514`/`claude-sonnet-4-5-20250929`（`:89`） | ✅ | `optional` / `anthropic`，enable 带 `budget_tokens: 1024`（`:91`） | — | — |
| `deepseek` | `deepseek-v4-flash`/`deepseek-v4-pro`/`deepseek-flash`（`:93`） | — | `optional` / `openai_extra_body` / `history=preserve` | `low,medium,high,max,xhigh`，默认 `low`，**`minimal→low` 别名**（`:99`） | — |
| `zai`、`zhipu-cn` | `glm-4.5`/`glm-4.6`/`glm-4.7`/`glm-5.3-flash`（`:100`） | — | `optional` / `openai_extra_body` | — | — |
| `doubao` | `doubao-seed-1-8-251228`（`:106`） | ✅ | `optional` / `openai_extra_body` | — | — |
| `moonshot-cn` | `kimi-k2.5`（`:113`） | ✅ | `optional` / `openai_extra_body` | — | `temperature=1.0`；enable 时 `temperature=1.0`、disable 时 `temperature=0.6`（`:117-119`） |
| `moonshot-cn` | `MOONSHOT_K31_MODELS` = `{"kimi-k3.1-pro", "kimi-k3.1-pro-highspeed"}`（`:15`） | ✅ | **`required`** / `none` / `history=preserve` | `low,high,max`，默认 `max`，**无别名**（`:124`） | 无 `when_thinking_disabled`（`:121-125`） |
| `minimax`、`minimax-cn` | `MiniMax-M2.7`/`MiniMax-M2.7-highspeed`（`:126`） | — | **`required`** / `none` | — | — |
| `minimax`、`minimax-cn` | `MiniMax-M3`（`:128`） | ✅ | `optional` / `none`；enable = `adaptive`（`:132`） | — | — |

docstring 明确写了为什么不能放宽成子串匹配（`:84`）：*"Do not broaden these to substrings."* 理由来自 `models/AGENTS.md`：`kimi-k3.1-pro-preview` 这类 ID 形状相同但厂商不承诺同样的能力；`tests/test_managed_moonshot.py:226-230` 钉死 `kimi-k2.5`/`unknown`/`kimi-k3.1-pro-preview` 三个 ID 各自不同的能力。

**adapter 是 provider 级、能力是 model 级**（`:83-84`）—— 因为 adapter 决定 wire 格式与 history 字段的处理方式，换 adapter 会破坏多轮一致性；而 thinking/vision/effort 是模型自己的属性。

### DeepSeek 的 `minimal → low` 别名（issue #4514）

`_capabilities` 为 deepseek 声明的 effort 词表是厂商原生集合，`aliases={"minimal": "low"}`（`:99`）。原因：DeerFlow 通用层把 `minimal` 当作「最省」的通用取值（legacy OpenAI-compat disable 路径会合成 `reasoning_effort="minimal"`），而 DeepSeek 官方端点**不接受** `minimal` 这个词。别名让保存下来的 per-agent 默认值在序列化后仍是官方端点认可的值。`tests/test_managed_deepseek.py:218-233` 逐个参数化 `minimal/low/medium/high/max/xhigh` 并断言 `reasoning.effort.aliases == {"minimal": "low"}`。

## 旧端点契约（legacy 兼容）

`resolve_managed_model_provider(base_url)`（`:66-77`）是**给 v2.1 之前保存的加密 `openai-compatible` 记录用的**，读路径不迁移 catalog：

- 命中 `_is_official_deepseek_endpoint()`（`:59-63`，要求 `https` + 主机 **严格等于** `api.deepseek.com` + 端口 ∈ {None, 443} + path.rstrip("/") ∈ {"", "/v1"}）→ 返回 DeepSeek 适配器 + thinking 模板；
- 否则 → `{"use": _OPENAI, "base_url": base_url}`。

判定**只看端点、不看模型 ID**。`tests/test_managed_deepseek.py:248-256` 列了 6 个反例（`api.deepseek.com.example.org`、`other.api.deepseek.com`、`/anthropic`、`/proxy/v1`、`:8443`、…）证明它们**不会**获得 DeepSeek 专属参数。

### Moonshot K3.1 的最终请求归一化在哪

不在 `managed_model_providers.py`，而在适配器 `models/patched_deepseek.py:23-47`：

- `_is_moonshot_k31_request(api_base, payload)`（`:23`）同时检查 **官方端点**（`https` + `api.moonshot.cn` + 端口 {None,443} + `/v1`）与**实际发送的模型 ID** —— 后者优先取 `extra_body.model` 覆盖值，其次 `payload["model"]`；
- `_normalize_moonshot_k31_payload(payload)`（`:36`）从顶层与 `extra_body` 两级删除 `{"thinking", "temperature", "top_p", "n", "presence_penalty", "frequency_penalty"}`，并**复制** `extra_body` 以免改动调用方持有的 mapping（OpenAI SDK 最后合并 `extra_body`，所以顶层删了不够）。

这条「provider 注册表 ↔ 适配器」的单向依赖值得记住：`patched_deepseek.py:20` 从 `deerflow.config.managed_model_providers` 导入 `MOONSHOT_K31_MODELS`，共享同一个 frozenset 而不是各写一份。

## `runtime_config()`：profile → `ModelConfig`

`ManagedModel.runtime_config()`（`managed_models.py:107-135`）：

```
api_key = api_key.get_secret_value()
if provider == "openai-compatible":
    settings = {**resolve_managed_model_provider(base_url), "api_key": api_key or "not-required"}
else:
    if not api_key: raise ValueError("This provider requires an API key")
    settings = resolve_preset_model(provider, model, api_key)
if reasoning is not None:          # 管理员显式声明的契约优先
    丢弃 reasoning / supports_thinking / supports_reasoning_effort（legacy 派生字段）
    thinking == "unsupported" → 丢弃 when_thinking_enabled
    thinking == "required"    → 丢弃 when_thinking_disabled
    settings["reasoning"] = self.reasoning
if supports_vision is not None: settings["supports_vision"] = ...
if max_tokens is not None:      settings["max_tokens"] = ...
return ModelConfig(name=name or "connection-check", display_name=..., model=..., context_window=..., **settings)
```

`resolve_preset_model(provider, model, api_key)`（`managed_model_providers.py:138-142`）：

```python
preset = get_managed_model_provider(provider)
if preset.endpoint is None:
    raise ValueError("Custom providers require an endpoint")
return {"use": preset.adapter, preset.endpoint_parameter: preset.endpoint,
        preset.auth_parameter: api_key, **deepcopy(preset.defaults), **_capabilities(provider, model)}
```

注意 **`deepcopy(preset.defaults)`**：`defaults` 是 dataclass 字段（`field(default_factory=dict)`，`:27`），若浅合并，某次运行时改动会污染后续所有 profile。

`"api_key": api_key or "not-required"` 是 `openai-compatible` 的既有语义：没配密钥时不从环境变量兜底，而是发一个字面量 `not-required`，让上游自行 401。`tests/test_managed_deepseek.py:279-288` 用 `monkeypatch.setenv("DEEPSEEK_API_KEY", ...)` / `OPENAI_API_KEY` 证明**环境凭据不会被借用**（`authorization: Bearer not-required`，结果是 `authentication_failed`）。

## 加密存储：`ManagedModelStore`

| 成员 | 行 | 行为 |
|------|----|------|
| `path` | `:153` | `runtime_home()/managed-models/catalog.enc` |
| `key_path` | `:154` | 同目录 `key` |
| `_cipher(create=False)` | `:156-167` | 惰性 import `cryptography.fernet`；key 文件不存在或内容是空白时：`create=True` **且** catalog 不存在 → 用 `read_or_create_secret_file()` 生成（独占创建、`0600`、硬链接语义）；否则抛 `ValueError("Managed model encryption key is missing; restore it from backup")` |
| `list()` | `:169-177` | 文件不存在 → `[]`；解密 + `json.loads` + 逐条 `ManagedModel.model_validate`；**任何**异常 → `ValueError("Cannot read managed models; check the catalog and encryption key")`（`from None`，绝不带解密后的输入） |
| `save(config, *, expected_revision, reserved_names=None)` | `:179-213` | 见下 |
| `_write(path, content)` | `:216-230` | `NamedTemporaryFile(dir=...)` + `flush` + `fsync` + `os.replace`；`finally` 里 `cleanup_failed_atomic_write()` 保证清理失败不覆盖写失败 |

`save()` 的事务边界是 `with _lock, extensions_config_file_lock(self.path)`（`:180`）—— **进程内 `RLock` + 跨进程 sidecar 文件锁**。`tests/test_managed_models.py:320`（`test_separate_process_writers_share_catalog_lock`）与 `test_managed_provider_presets.py:126`（`test_auto_names` 系列）分别钉死跨进程和锁内分配。

`save()` 的分支语义：

1. **自动命名**（`:182-191`）：`name == ""` 且 `expected_revision is None` → 用 `{provider}-{slug}-{uuid4().hex[:12]}`（slug = `re.sub(r"[^A-Za-z0-9_.-]+", "-", model)`，截到 85 字符后拼 12 位随机后缀），在 `records ∪ reserved_names` 内查重。`name == ""` + `expected_revision` 非空 → `ManagedModelInputError("An existing model name is required when editing")`。
2. **revision 乐观锁**（`:192-196`）：`previous is None` + `expected_revision` 非空 → `FileNotFoundError`；`previous` 存在但 `expected_revision is None` **或** 不匹配 → `FileExistsError`。也就是说**编辑必须带 revision**，不带视为冲突而不是「无脑覆盖」。
3. **密钥保留**（`:197` + `retained_api_key()` `:142-148`）：`config.api_key` 非空 → 用它；否则仅当 `(provider, base_url)` 都没变才继承旧密钥 —— **换 provider 或换自定义端点一律丢弃旧密钥**。
4. **preset 必须有关键字**（`:198-199`）：`provider != "openai-compatible"` 且 `enabled` 且密钥为空 → `ManagedModelInputError("This provider requires an API key; enter a key or disable the model")`。
5. **写盘前先验证能力覆盖**（`:202-207`）：`candidate = config.model_copy(update={"api_key": secret})`，仅当 `enabled` 时试跑 `candidate.runtime_config()`，抛 `ValueError` → `ManagedModelInputError("Invalid model capability overrides")`。这条让「存进去之后每次 chat 都炸」变成「保存时就 422」；已 disabled 的条目允许留着待修。
6. 追加/替换记录（`:209`）、`display_name` 兜底 + `revision = uuid4().hex`（`:208`）、序列化成明文 JSON（`api_key` 单独展开成字符串，`:210`）、Fernet 加密（`:211`）、原子写（`:212`）。

### 密钥文件的两个恢复边界

代码注释里写得很细（`:159-166`）：

- **空 key 文件且 catalog 不存在** = 老版本首次保存被打断，它什么都没加密过 → 可以恢复，重新生成（`tests/test_managed_models.py:82-94`）。
- **空 key 文件但 catalog 存在** → **绝不替换**，直接报错（`:97-109`）。新 key 会让既有 catalog 永久无法解密，这比 503 更糟。
- **并发首次保存**：`read_or_create_secret_file` 的独占创建语义保证先发布者赢（`tests/test_managed_models.py:63-79`）。

## 合并进有效配置：`merge_managed_models()`

`managed_models.py:233-249`：

```python
signature = (str(store.path), get_config_signature(store.path), get_config_signature(store.key_path))
if signature[1] is None:            # catalog 不存在 → 原样返回
    return config
with _lock:
    if _cache 命中 (同一 base config 对象 + 同一签名): return 缓存
    yaml_names = {item.name for item in config.models}
    managed = [item.runtime_config() for item in store.list() if item.enabled and item.name not in yaml_names]
    result = config.model_copy(update={"models": [*config.models, *managed]})
    result._models_by_name = {**config._models_by_name, **{m.name: m for m in managed}}
    result._managed_model_names = {m.name for m in managed}
    return result
```

要点：

- **YAML 优先**：同名 managed 条目被过滤（`item.name not in yaml_names`），不是覆盖。
- **永不修改 base config**：`model_copy` 生成新对象。`tests/test_managed_models.py:41-52` 断言旧快照 `merged` 在 managed 被 disable 之后仍能看到该模型，而 `base` 从头到尾都看不到。
- **`_managed_model_names` 是私有来源元数据**（`app_config.py:417` 声明为 `PrivateAttr`），供路由判断「这个名字是不是 YAML 保留的」用，**不是** provider kwarg。
- 缓存键含 base config 的**对象身份**（`_cache[0] is config`），所以 `set_app_config()` 注入的配置永远拿到自己的合并结果。
- `AppConfig.from_file()` **不**做合并 —— 只有 `get_app_config()`（`app_config.py:839-841`）与 `reload_app_config()`（`:865`、`:879`）在返回值前调用它。所以「直接读 YAML」与「运行时生效配置」是两条路径，前者永远干净。

## HTTP 面：`/api/managed-models`（`app/gateway/routers/managed_models.py`）

### 鉴权

四个端点全部以 `await require_admin_user(request, detail=_ADMIN)` 开头（`:70`、`:76`、`:116`、`:159`），`_ADMIN = "Admin privileges are required to manage shared models."`（`:40`）。

`require_admin_user` → `is_admin_user`（`app/gateway/deps.py:1414-1439`）的两条否决：

1. `request.state.auth_source == AUTH_SOURCE_PAT` → 直接 `False`（**PAT 没有 admin 能力，管理员的自动化 token 也不能开这道门**）；
2. `getattr(user, "system_role", None) == "admin"`。

`tests/test_managed_models.py:264-282` 同时钉住两件事：YAML 保留名 → 409，以及把 `auth_source` 切成 PAT 之后 `save_model` 与 `test_model` 都变 403（且 catalog 文件从未被创建）。`test_managed_provider_presets.py:151-159` 用 `system_role="user"` 断言 403。

### 端点表

| 方法/路径 | 行 | 请求体 | 成功响应 | 失败 |
|-----------|----|--------|---------|------|
| `GET /providers` | `:68-71` | — | `{"providers": [provider.public() ...]}`（4 键，无路由信息） | 403 |
| `GET ""` | `:74-80` | — | `_catalog()`：YAML 模型（`source: "config"`）+ managed 模型（`item.public()` + `conflict`） | 403 / **503** "Managed model storage is unavailable; check the catalog and encryption key" |
| `PUT ""` | `:114-117` | `SaveModelRequest` | `ManagedModel.public()`（含 `revision`） | 403 / 422 / 404 / 409 / 503 |
| `POST /test` | `:156-182` | `SaveModelRequest` | `{"ok": bool, "message": str}` —— **永远是 200** | 403 / 409（stale revision）/ 422（路由级） |

`_catalog()`（`:58-65`）的合并逻辑：YAML 侧过滤掉 `config._managed_model_names` 里的名字（这些其实是合并进来的托管模型），managed 侧给每条加 `conflict: item.name in yaml_names` —— 前端据此提示「这个名字已被 config.yaml 占用，不会生效」。注意它**同时读** `get_app_config()` 与 `ManagedModelStore().list()`，所以能在 503 之前先失败在 catalog 上。

### `SaveModelRequest` 的两道门（`:43-55`）

```python
class SaveModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: ManagedModel
    expected_revision: str | None = None

    @model_validator(mode="before")
    def reject_preset_routes(cls, value):
        if isinstance(value, dict):
            config = value.get("config")
            if isinstance(config, dict) and config.get("provider", "openai-compatible") != "openai-compatible" and "base_url" in config:
                raise ValueError("Preset endpoints cannot be overridden")
```

- `extra="forbid"` → 客户端塞 `use` / `api_base` / `default_headers.Authorization` 全被拒（`test_managed_provider_presets.py:66-70`、`:397-400`）；
- `reject_preset_routes` 在 **before** 阶段拦下 preset + `base_url`，比 `ManagedModel.validate_routing`（`managed_models.py:96-105`）更早，为的是在 FastAPI 把输入拼进 `RequestValidationError` 之前就拒绝。

### `RedactedModelRoute`：为什么需要自定义 APIRoute（`:24-36`）

FastAPI 默认的 `RequestValidationError` 处理器会把**整个输入**（`input`）塞进 422 响应体 —— 对 `PUT /api/managed-models` 而言那就是一份带明文 `api_key` 的草稿。于是路由用 `route_class=RedactedModelRoute`（`:39`）把任何 `RequestValidationError` 替换成固定结构：

```json
{"code": "invalid_model", "message": "Invalid model configuration; check provider, model ID and capability fields"}
```

`tests/test_managed_provider_presets.py:161-181` 用真实 ASGI 客户端跑四条非法草稿，断言响应文本里既没有 `private-test-key` 也没有 `**********`，也没有 `evil`。这是本路由**唯一**一处「用 HTTP 层兜住 pydantic 回显」的地方。

### `PUT` 的状态码映射（`_save`，`:83-97`）

| 异常 | 状态码 | detail |
|------|--------|--------|
| 名字与 YAML 模型重名（且不在 `_managed_model_names`） | 409 | `"This model name is reserved by config.yaml"` |
| `ManagedModelInputError` | 422 | `{"code": "model_key_or_capabilities", "message": str(exc)}` |
| `FileExistsError` | 409 | `"Model changed or already exists; reload before saving"` |
| `FileNotFoundError` | 404 | `"Model no longer exists"` |
| `ValueError` / `OSError` | 503 | `"Managed model storage is unavailable"` |

`reserved_names` 在 `:87` 计算后传给 `store.save()`，让**自动命名**也避开 YAML 名字（`test_managed_provider_presets.py:325` 用它构造冲突重试）。

### 失败不丢：`run_drained_write` + `_save_with_failure_logging`

```python
@router.put("")
async def save_model(request, body):
    await require_admin_user(request, detail=_ADMIN)
    return await run_drained_write("Save managed model", _save_with_failure_logging, (HTTPException,), body)
```

`run_drained_write`（`app/gateway/persistent_writes.py:18-47`）把同步函数丢进 `asyncio.to_thread`，再用 `await_drained` 等它跑完 —— 客户端断连触发的 task cancel **不会**取消一个还在队列里的写线程，也不会因为 handler 的 `except` 没机会跑而吞掉失败。`expected_errors=(HTTPException,)` 表示领域错误原样上抛（handler 还连着时映射成 4xx），其它异常由 `persistent_writes` 记一条**只带异常类型**的日志。

`_save_with_failure_logging`（`:100-111`）补了一层：

```python
except HTTPException as exc:
    if exc.status_code >= 500: logger.error(...)     # 5xx 也记
    raise
except Exception as exc:
    logger.error("Managed model save failed (%s)", type(exc).__name__)   # 只留类型
    raise
```

注释解释了为什么只留类型：*"Storage exceptions can contain credentials"*。`tests/test_managed_models.py:119-195` 覆盖了「已启动的写在重复 cancel 下仍完成」和「cancel 之后的失败仍被记录」。

## Probe：`POST /test`

### 为什么复用 factory（`_build_probe`，`:133-153`）

docstring 一句话：*"Use exactly the same resolution, reasoning transforms and factory as chat."* 具体：

1. `_probe_config(body)`（`:120-130`）：
   - 若带 `expected_revision`，先比对 catalog 里同名条目的 `revision`，不一致 → **409**（`"Model changed; reload before testing"`），且是在**任何 provider 接触之前**；
   - `profile.model_copy(update={"api_key": retained_api_key(profile, previous)})` —— 草稿里没给 key 时用已保存的 key（换 provider/端点则不继承）；
   - `provider != "openai-compatible"` 且无 key → `ManagedModelInputError("This provider requires an API key")`。
2. `resolve_reasoning_contract(config)`（`:136`）拿 `thinking_required`。
3. `force_tool = not required and (provider in {"openai-compatible","openai","anthropic"} or config.when_thinking_disabled is not None)`（`:142`）。两条保守规则都写在注释里：required-thinking 的模型**不接受**强制 tool 选择；未知第三方模型（第三方 preset 上未识别的 ID）没有经过验证的强制 tool 能力，用 `auto` 而不是编一个契约。
4. **新建一个只有这一个模型的 `AppConfig`**（`:143`），sandbox 塞 `LocalSandboxProvider`；
5. `create_chat_model(..., thinking_enabled=False, attach_tracing=False, model_overrides={"timeout": 15, "max_retries": 0, "max_tokens": 2048 if required else 32})`；
6. `bind_tools([connection_check], tool_choice="connection_check" if force_tool else "auto")`。

`attach_tracing=False`（测试 `test_managed_models.py:308` 断言）保证 probe 不会往 Langfuse 里写一条假 trace。

### 有界流式读取与判定（`:156-182`）

```
asyncio.timeout(20)                       # 总预算
  probe = await asyncio.to_thread(_build_probe, body)   # 构造（含 SDK client 创建）不占事件循环
  async with aclosing(probe.astream([HumanMessage("Call connection_check.")], config={"callbacks": []})) as stream:
      async for chunk:
          size += len(str(content)) + len(str(tool_call_chunks)) + len(str(additional_kwargs))
          chunks += 1
          if size > 16384 or chunks > 256: return {"ok": False, "message": "response_limit"}
          response = chunk if response is None else response + chunk
  …判断任何 tool_call 的 name == "connection_check" 且 args == {}
```

返回的四种 `message`：

| message | 触发 |
|---------|------|
| `success` | 收到 `connection_check` 且参数为 `{}` |
| `tool_call_missing` | 流结束但没有符合要求的 tool call（包括模型只回了文本） |
| `response_limit` | 超过 16384 字符或 256 个 chunk |
| `missing_api_key` | `ManagedModelInputError`（`_probe_config` 抛的） |
| `authentication_failed` | 异常对象带 `status_code in (401, 403)` |
| `connection_failed` | 其它任何异常 |

异常分支的注释（`:181-182`）：*"Provider exception strings may contain keys, URLs or response bodies."* —— 所以**永不**回显 `str(exc)`，连类型都不回显。`tests/test_managed_models.py:285-318` 用 `RuntimeError("test-secret should never be returned")` 断言返回体里没有 `test-secret`；`test_managed_provider_presets.py:286-293` 断言原生/兼容两条协议的 401/403 都被压成 `authentication_failed` 且**不重试**（`max_retries=0`，HTTP double 只看到 1 个请求）。

**probe 从不写盘**：整个 handler 没有任何 `store.save` 调用，`test_managed_deepseek.py:85-160` 里每个 probe 测试都以 `assert not store.path.exists()` 结尾。

### 为什么 `max_tokens` 分 32 / 2048

required-thinking 的模型即使只要求「调一个空参数工具」也要为 thinking 留预算，32 token 会在 thinking 阶段就被截断，probe 必然 `tool_call_missing`。`tests/test_managed_provider_presets.py:274-285`（`test_required_thinking_uses_auto_selection_and_bounded_budget`）钉死这个分叉。

## 同步 / 阻塞 I/O 边界

`tests/blocking_io/test_managed_models.py` 用 Blockbuster 风格门禁证明三件事都不在事件循环上：

1. `test_admin_catalog_round_trip_offloads_storage`（`:18`）—— `PUT` + `GET` 全流程（加密、解密、原子写）在 worker 线程；
2. `test_deepseek_probe_offloads_credentials_and_client_construction`（`:32`）—— 在 `ChatOpenAI.__init__` / `PatchedChatDeepSeek.__init__` 里断言 `asyncio.get_running_loop()` 抛 `RuntimeError`，即 **SDK client 构造发生在无 loop 的线程**；
3. `test_preset_catalog_registration_and_native_client_stay_off_loop`（`:78`）。

路由里对应的三个 off-loop 点：`GET ""` 的 `asyncio.to_thread(_catalog)`（`:78`）、`PUT` 的 `run_drained_write`、`POST /test` 的 `asyncio.to_thread(_build_probe)`（`:165`）。

## 与相邻机制的关系

| 相邻机制 | 关系 |
|---------|------|
| `create_chat_model()`（`models/factory.py`） | probe 与真实 chat 的唯一入口。provider 的 `use` 类路径来自注册表，`base_url`/`api_base`/`when_thinking_*` 来自 `ModelConfig.model_extra`；reasoning 契约由 `resolve_reasoning_contract()` 解释 |
| `ReasoningContract`（`models/reasoning.py`） | `runtime_config()` 输出的 `reasoning` mapping 就是它声明的契约；`dialect=none`（K3.1、MiniMax）表示「不发 thinking 开关，模型天生如此」 |
| `get_app_config()` / `reload_app_config()` | 托管的唯一注入点（`app_config.py:839`/`:865`）；`AppConfig.from_file()` 不合并 |
| `/api/models`（`app/gateway/routers/models.py`） | 读同一个有效快照，因此托管模型会**自动出现**在模型列表里，且列表里没有明文密钥（`test_managed_provider_presets.py:336` 断言 `private-test-key` / `yaml-test-key` 都不出现在响应里） |
| `authz.authorize_model_use` / `model:use` | 托管模型纳入同一个鉴权决策面；`_managed_model_names` 只是来源元数据，不参与鉴权 |
| Custom Agent 的 `model` 字段 | `_validate_model_exists` 用 `app_config.get_model_config(name)` 校验，所以托管模型可以直接被 agent 引用（先保存、再引用） |
| `patched_deepseek.py` | 反向依赖注册表的 `MOONSHOT_K31_MODELS`，做最终 wire 归一化（见上） |
| 运行器 `RunManager` | 无关：每次 `create_chat_model` 都新建实例，catalog 变更不影响已开始的 run（`merge_managed_models` 只产出新快照） |

## 测试地图

| 测试文件 | 覆盖 |
|---------|------|
| `tests/test_managed_models.py`（345 行） | 加密/密钥/revision（`:26`）、YAML 优先级与 disable（`:41`）、key 文件四种恢复边界（`:55`-`:109`）、端点校验（`:112`）、drain（`:119`/`:155`）、admin + 不泄漏（`:196`）、配置热读（`:216`）、并发写（`:239`）、清 key 与损坏 catalog fail-closed（`:250`）、YAML 保留名 + PAT 403（`:264`）、probe 边界（`:285`）、跨进程锁（`:320`） |
| `tests/test_managed_provider_presets.py`（411 行） | 8 个 preset 的路由与保守能力（`:40`）、自动命名（`:51`）、preset 拒绝路由覆盖（`:66`）、未知 provider（`:72`）、换 provider 不复用 key（`:77`）、旧 catalog 兼容（`:93`）、锁内命名（`:126`）、注入配置权威性（`:135`）、admin（`:151`）、422 不回显（`:161`）、真实 SDK 协议 + 认证（`:221`）、probe vs chat 的 thinking 差异（`:263`）、required thinking 的 auto 选择（`:274`）、错误压平不重试（`:286`）、缺 key 不打 provider（`:294`）、revision + 换 provider（`:305`）、响应体积上限（`:320`）、与 YAML 撞名重试（`:325`）、API 保存/刷新/409/disable 全链（`:336`）、reasoning 不得覆盖路由与凭据（`:397`） |
| `tests/test_managed_deepseek.py`（311 行） | probe 的请求形状（`:85`）、必须有正确 tool（`:107`）、不重试不泄漏（`:117`）、timeout 与 cancel 区分（`:127`）、草稿 vs 已存 key（`:138`）、stale revision 先于 provider（`:153`）、鉴权先于 provider（`:164`）、已存模型的流式 reasoning（`:182`）、effort 别名（`:218`）、非官方端点不加 DS 参数（`:257`）、通用 probe 契约（`:269`）、不借环境凭据（`:279`）、流中途失败不算成功（`:289`） |
| `tests/test_managed_moonshot.py`（271 行） | K3.1 契约（`:89`）、四个公开路径的 wire 默认值（`:107`）、原生 effort 词表与契约兜底（`:123`）、固定采样键不能被重新引入（`:132`）、thinking 在每种显式开关下都被省略（`:162`）、直接构造 adapter（`:171`）、不可变 `extra_body` + 有效模型覆盖（`:198`）、官方端点形态（`:210`）、非官方端点不重写（`:217`）、其它 ID 保持原能力（`:226`）、`extra_body.model` 决定契约（`:236`）、图片 tool follow-up（`:253`） |
| `tests/blocking_io/test_managed_models.py`（111 行） | 存储往返、DeepSeek probe、preset 注册与原生 client 均 off-loop |
| `tests/test_provider_credentials_single_owner.py`（253 行） | **相邻机制**：`community/` 里 LightRAG/RAGFlow 三条凭据规则的单一所有者（`resolve_api_key` / `redact_secret` / `reject_url_userinfo`）。其模块 docstring（`:20-26`）**显式**把 `config/managed_models.py` 的 `get_secret_value()` 排除在普查范围外（"unwrap for other reasons"）—— 所以不要误以为它测的是托管模型 |

## 陷阱清单

1. **不要在 `_capabilities` 里用子串匹配**。`:84` 的注释与 `test_managed_moonshot.py:226` 都钉着这一点；`kimi-k3.1-pro-preview` 必须保持 `unsupported`。
2. **`endpoint_parameter` 分两种**：OpenAI 系是 `base_url`，DeepSeek 系（含 Qwen/Doubao/Moonshot/Zhipu/ZAI）是 `api_base`。写错时 factory 不报错，只是请求打到默认端点。
3. **换 provider 或换自定义端点必须丢旧 key**（`retained_api_key`，`:146`），否则旧厂商的密钥会被发到新端点。
4. **`base_url` 的 userinfo 已被禁**（`ManagedModel.valid_endpoint`，`:62`）—— 这一条与 `community/provider_credentials.py` 的 `reject_url_userinfo` 是**两套独立实现**，各自属于各自的层。
5. **probe 失败不是 4xx**：`POST /test` 的 provider 级失败一律 200 + `{"ok": false, "message": ...}`，只有权限、stale revision 与请求体校验才会给 403/409/422。前端据此区分「配置错」与「连不上」。
6. **`GET ""` 的 503 有两个来源**：`_catalog()` 里 `ManagedModelStore().list()` 抛 `ValueError`（密钥缺失/损坏），或 `get_app_config()`（会调用 `merge_managed_models`，同样的 `ValueError`）。两者都压成同一条 detail，不区分。
7. **管理端 422 有两套形状**：路由级（`RedactedModelRoute`）是 `{"code": "invalid_model", "message": ...}`；业务级（`ManagedModelInputError`）是 `{"code": "model_key_or_capabilities", "message": ...}`。两者都是对象 detail，不是字符串。
8. **`display_name` 空值时服务端补**：`save()`（`:200`）和 `runtime_config()`（`:131`）各算一次，前者持久化、后者兜底 —— 改文案时两处要一起改。
