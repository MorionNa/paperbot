# paperbot

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
