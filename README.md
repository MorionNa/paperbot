# paperbot

## Fulltext 下载能力

当前下载路由支持以下 publisher/API：

- Wiley TDM（`WILEY_TDM_CLIENT_TOKEN`）
- Springer Nature TDM（`SPRINGER_API_KEY`）
- Elsevier Full Text API（`ELSEVIER_API_KEY`，可选 `ELSEVIER_INSTTOKEN`）
- IEEE API（`IEEE_API_KEY`）
- Crossref text-mining link（兜底）

## 各 Publisher API 配置说明（统一）

- **Wiley**
  - 环境变量：`WILEY_TDM_CLIENT_TOKEN`
  - 说明：Wiley DOI 在 `run_daily.py` 中优先走 tdm-client 批量下载。

- **Springer Nature**
  - 环境变量：`SPRINGER_API_KEY`
  - 说明：Springer DOI 优先走 TDM XML 下载。

- **Elsevier**
  - 环境变量：`ELSEVIER_API_KEY`
  - 可选：`ELSEVIER_INSTTOKEN`
  - 说明：通过 Elsevier Full Text API 下载 XML。

- **IEEE**
  - 环境变量：`IEEE_API_KEY`
  - 说明：通过内置 IEEE API 模板 URL 下载 XML：
    `https://ieeexploreapi.ieee.org/api/v1/search/articles?doi={doi}&apikey={api_key}&format=xml`

## IEEE API 快速下载全文

当 DOI 满足以下任一条件时，会自动进入 IEEE 下载器：

- DOI 前缀是 `10.1109/`
- `article.publisher` 包含 `IEEE` / `Institute of Electrical and Electronics Engineers`

程序会对 DOI/API Key 做 URL 编码并替换模板参数，优先请求 `application/xml`，保存到：

- `data/fulltext/ieee/<doi_sha1>.xml`
