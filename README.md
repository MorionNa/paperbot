# paperbot

## Fulltext 下载能力

当前下载路由支持以下 publisher/API：

- Wiley TDM（`WILEY_TDM_CLIENT_TOKEN`）
- Springer Nature TDM（`SPRINGER_API_KEY`）
- Elsevier Full Text API（`ELSEVIER_API_KEY`，可选 `ELSEVIER_INSTTOKEN`）
- IEEE API（`IEEE_API_KEY`）
- Crossref text-mining link（兜底）

## 各 Publisher 下载机制与配置说明（统一）

- **Wiley（Wiley TDM）**
  - 环境变量：`WILEY_TDM_CLIENT_TOKEN`
  - 下载机制：在 `run_daily.py` 中，Wiley DOI 会先进入待下载队列，随后通过 `wiley-tdm` 客户端批量下载 PDF，并写入 `fulltexts` 表。
  - 典型存储：由 `wiley-tdm` 运行目录产物决定（项目中默认在 `data/wiley_tdm_runs/.../downloads`）。

- **Springer Nature（Springer TDM）**
  - 环境变量：`SPRINGER_API_KEY`
  - 下载机制：命中 Springer DOI 后优先走 Springer TDM JATS XML 接口；若失败再回退到原有 PDF 逻辑。
  - 典型存储：`data/fulltext/springer_tdm/<doi_sha1>.xml`（TDM XML 成功时）。

- **Elsevier（Elsevier Full Text API）**
  - 环境变量：`ELSEVIER_API_KEY`
  - 可选：`ELSEVIER_INSTTOKEN`
  - 下载机制：命中 Elsevier DOI 后，通过 `content/article/doi` 接口请求全文 XML（`view=FULL`）。
  - 典型存储：`data/fulltext/elsevier/<doi_sha1>.xml`。

- **IEEE（IEEE Xplore API）**
  - 环境变量：`IEEE_API_KEY`
  - 下载机制：命中 IEEE DOI 或 IEEE publisher 后，使用内置 IEEE API 模板 URL 拉取 XML：
    `https://ieeexploreapi.ieee.org/api/v1/search/articles?doi={doi}&apikey={api_key}&format=xml`
  - 典型存储：`data/fulltext/ieee/<doi_sha1>.xml`。

- **Crossref（fallback）**
  - 环境变量：无必填（可配 Crossref mailto 等发现参数）
  - 下载机制：若未命中上述 provider 专用下载器，则尝试从 Crossref `raw.link` 中选择 `intended-application=text-mining` 链接（优先 XML）下载。
  - 典型存储：`data/fulltext/crossref/<doi_sha1>.xml`。

## IEEE API 快速下载全文

当 DOI 满足以下任一条件时，会自动进入 IEEE 下载器：

- DOI 前缀是 `10.1109/`
- `article.publisher` 包含 `IEEE` / `Institute of Electrical and Electronics Engineers`

程序会对 DOI/API Key 做 URL 编码并替换模板参数，优先请求 `application/xml`，保存到：

- `data/fulltext/ieee/<doi_sha1>.xml`
