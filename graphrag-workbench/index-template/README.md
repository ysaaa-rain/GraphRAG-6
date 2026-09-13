# 新建索引的模板

把这个文件夹整个复制成你自己的索引目录，就是一个合法的 GraphRAG 工程。

## 用法

1. 复制成自己的目录，例如 `D:\myrag`
2. 在里面建 `input\`，把自己的 `.jsonl` 放进去（每行一篇文档）
3. 从仓库根复制 `.env.example` 成 `.env`，填上自己的 DeepSeek 密钥
4. 数据不在 `input\` 里的话，改 `settings.yaml` 的 `input_storage.base_dir`

建完之后目录长这样：

```
D:\myrag\
├── input\              ← 你的数据（每行 {"id": "...", "title": "...", "text": "..."}）
├── prompts\            ← 13 个提示词，不用改
├── settings.yaml       ← 配置，通常只改 input_storage.base_dir
├── .env                ← 你自己的密钥
├── output\             ← 建完索引自动出现
├── lancedb\            ← 建完索引自动出现
└── cache\ logs\        ← 建完索引自动出现
```

## 数据格式

一行一个 JSON 对象，字段名要和 `settings.yaml` 里的 `id_column / title_column / text_column` 对上：

```json
{"id": "mail-001", "title": "邮件主题", "text": "邮件正文……"}
```

一份 `output\` 和 `lancedb\` 只属于一份数据。换数据就要换个目录重建，不要在同一个目录里混两批数据。
