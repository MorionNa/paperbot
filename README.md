# paperbot

## Fulltext 下载能力

当前下载路由支持以下 publisher/API：

- Wiley TDM（`WILEY_TDM_CLIENT_TOKEN`）
- Springer Nature TDM（`SPRINGER_API_KEY`）
- Elsevier Full Text API（`ELSEVIER_API_KEY`，可选 `ELSEVIER_INSTTOKEN`）
- **ACM API（新增）**
- Crossref text-mining link（兜底）

## ACM API 快速下载全文（新增）

当 DOI 满足以下任一条件时，会自动进入 ACM 下载器：

- DOI 前缀是 `10.1145/`
- `article.publisher` 包含 `Association for Computing Machinery` / `acm`

### 需要配置的环境变量

- `ACM_API_KEY`：ACM API token
- `ACM_API_URL_TEMPLATE`：ACM API 地址模板，必须包含 `{doi}` 占位符

示例：

```bash
export ACM_API_KEY="<your-acm-api-key>"
export ACM_API_URL_TEMPLATE="https://api.acm.org/dl/v1/articles/{doi}/fulltext"
```

程序会对 DOI 做 URL 编码并替换 `{doi}`，以 `application/xml` 优先请求并保存到：

- `data/fulltext/acm/<doi_sha1>.xml`
