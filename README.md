# paperbot

## 使用方法

### 1) 准备配置

1. 安装依赖（建议在虚拟环境中）。
2. 配置 `config/config.yml`，至少包含：
   - `pipeline.db_url`
   - `pipeline.journals`
   - `pipeline.lookback_days`（或 `pipeline.date_from` + `pipeline.date_until`）
   - `summarize.*`
   - `llm.*`
3. 创建并配置 `config/secrets.yml`（推荐），脚本启动时会自动加载到环境变量。示例：

```yaml
openai_api_key: "<your-openai-key>"
gemini_api_key: "<your-gemini-key>"
anthropic_api_key: "<your-anthropic-key>"
dashscope_api_key: "<your-dashscope-key>"
elsevier_api_key: "<your-elsevier-key>"
elsevier_insttoken: "<optional-insttoken>"
wiley_tdm_client_token: "<your-wiley-tdm-token>"
springer_api_key: "<your-springer-key>"
ieee_api_key: "<your-ieee-key>"
```

---

### 2) 运行 `run_daily.py`（发现论文 + 下载全文 + 导出 Excel）

在仓库根目录执行：

```bash
python app/run_daily.py
```

脚本会完成以下步骤：

- 从 `config/config.yml` 读取 pipeline 配置。
- 按期刊与时间范围抓取论文元数据并写入 SQLite（`articles`）。
- 根据 DOI / publisher 路由下载全文并写入 `fulltexts`。
- 导出“本次新增论文”的 Excel（文件名自动附加时间戳，默认在 `outputs/` 下）。

时间范围控制：

- 默认：`pipeline.lookback_days`
- 指定区间：同时设置 `pipeline.date_from` 与 `pipeline.date_until`（`YYYY-MM-DD`）

---

### 3) 运行 `summarize_papers.py`（对已解析正文做结构化总结）

在仓库根目录执行：

```bash
python app/summarize_papers.py
```

说明：

- 该脚本会读取 `parsed_texts` 中尚未成功总结（`summaries.status != 'ok'`）且正文长度足够的记录。
- 先分块生成 chunk 摘要，再合并生成结构化 JSON（`method_summary` / `result_summary` / `keywords` / `tags` 等）。
- 结果写入 `summaries` 表（成功为 `ok`，失败为 `failed`）。
- 每次处理上限由 `config.yml` 的 `summarize.limit_per_run` 控制。

## Fulltext 下载能力

当前下载路由支持以下 publisher/API：

- Wiley TDM（`WILEY_TDM_CLIENT_TOKEN`）
- Springer Nature TDM（`SPRINGER_API_KEY`）
- Elsevier Full Text API（`ELSEVIER_API_KEY`，可选 `ELSEVIER_INSTTOKEN`）
- IEEE API（`IEEE_API_KEY`）
- Crossref text-mining link（兜底）

## 各下载器机制与配置说明（统一）

- **Wiley（Wiley TDM）**
  - 命中规则：DOI 前缀 `10.1002/` 或 `10.1111/`
  - 环境变量：`WILEY_TDM_CLIENT_TOKEN`
  - 下载机制：在 `run_daily.py` 中先进入待下载队列，再通过 `wiley-tdm` 客户端批量下载 PDF，并写入 `fulltexts` 表。
  - 典型存储：由 `wiley-tdm` 运行目录产物决定（默认 `data/wiley_tdm_runs/.../downloads`）。

- **Springer Nature（Springer TDM）**
  - 命中规则：DOI 前缀 `10.1007/`
  - 环境变量：`SPRINGER_API_KEY`
  - 下载机制：优先走 Springer TDM JATS XML；若失败回退到原有 PDF 逻辑。
  - 典型存储：`data/fulltext/springer_tdm/<doi_sha1>.xml`（TDM XML 成功时）。

- **Elsevier（Elsevier Full Text API）**
  - 命中规则：DOI 前缀 `10.1016/`
  - 环境变量：`ELSEVIER_API_KEY`
  - 可选：`ELSEVIER_INSTTOKEN`
  - 下载机制：通过 `content/article/doi` 接口请求全文 XML（`view=FULL`）。
  - 典型存储：`data/fulltext/elsevier/<doi_sha1>.xml`。

- **IEEE（IEEE Xplore API）**
  - 命中规则：DOI 前缀 `10.1109/`，或 `publisher` 包含 `IEEE` / `Institute of Electrical and Electronics Engineers`
  - 环境变量：`IEEE_API_KEY`
  - 下载机制：使用内置模板 URL 拉取 XML：
    `https://ieeexploreapi.ieee.org/api/v1/search/articles?doi={doi}&apikey={api_key}&format=xml`
  - 典型存储：`data/fulltext/ieee/<doi_sha1>.xml`。

- **Crossref（fallback）**
  - 命中规则：未命中以上专用下载器时自动进入 fallback
  - 环境变量：无必填（可配 Crossref mailto 等发现参数）
  - 下载机制：从 Crossref `raw.link` 中选择 `intended-application=text-mining` 链接（优先 XML）下载。
  - 典型存储：`data/fulltext/crossref/<doi_sha1>.xml`。


## 文件命名规则

- 下载文件优先使用论文标题作为文件名（会自动清理不合法字符并截断）。
- 若标题为空或清理后为空，则回退为 DOI 的 SHA1。


## 按时间范围下载论文

`run_daily.py` 现在支持两种时间窗口配置：

- 默认模式：使用 `pipeline.lookback_days`（例如最近 30 天）
- 指定区间模式：同时设置 `pipeline.date_from` 和 `pipeline.date_until`（格式 `YYYY-MM-DD`）

示例（`config/config.yml`）：

```yaml
pipeline:
  lookback_days: 30
  date_from: "2024-01-01"
  date_until: "2024-01-31"
```

说明：
- 当 `date_from/date_until` 同时存在时，会覆盖 `lookback_days`。
- 两者必须同时配置，且 `date_from <= date_until`。

### 4) 图形界面（GUI）配置与一键运行

在仓库根目录执行：

```bash
python app/gui.py
```

GUI 提供三块功能：

- 添加期刊：填写期刊名称、publisher、ISSN 信息后点击“添加期刊”，会追加到 `config/config.yml` 的 `journals` 列表。
- 设置 API Key：支持 Elsevier / Wiley / Springer / IEEE，点击“确认保存 Key”后写入 `config/secrets.yml`。
- 指定时间运行：输入开始与结束时间（`YYYY-MM-DD`），点击“下载并运行”，会写入 `pipeline.date_from/date_until` 并自动执行 `app/run_daily.py`。

