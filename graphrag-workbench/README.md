# GraphRAG 工作台

纯前端，覆盖三件事：建索引（带阶段进度）、查看每个阶段的产物、多方法检索对照。
原上游演示界面（`unified-search-app`）已于 2026-09-13 删除；检索算法在独立包
`../graphrag6-retrieval` 里，这里只做界面和编排。

## 结构

```
app/main.py          Streamlit 界面（两个页签：建索引与阶段 / 检索对照）
app/index_view.py    索引阶段数据层，只依赖 pandas，可脱离 streamlit 测试
app/trace_view.py    证据链与子图渲染（把 trace 变成表格和 Graphviz DOT）
tests/               29 个测试；算法包的测试在 ../graphrag6-retrieval/tests
index-template/      新建索引的模板：settings.yaml + 13 个提示词，复制即用
```

检索算法（LightRAG 风格 / HippoRAG 2 风格 / Hybrid Path）在独立包
[graphrag6-retrieval](../graphrag6-retrieval)，本目录只 import 它，不重复实现。

## 快速开始（从零到跑通）

下面每一行命令都标了它在干什么。第一次请按顺序敲；**第 8 步那个窗口开始后就一直别关**。

### 一、一次性准备

**1. 装 uv**

```powershell
winget install astral-sh.uv
```

> 装个工具，后面所有 `uv` 都是它。装完把终端关掉重开。

**2. 下载项目**

```powershell
cd D:\
git clone <仓库地址> GraphRAG-6
```

> 到 D 盘，把整个项目下载成 `D:\GraphRAG-6`。

**3. 装前端的依赖**

```powershell
cd D:\GraphRAG-6\graphrag-workbench
uv sync
```

> 照清单把网页框架、GraphRAG 引擎、本项目的算法包（`../graphrag6-retrieval`）都装进这个文件夹。

验收（必须打印 `ok`）：

```powershell
uv run python -c "import graphrag6_retrieval, streamlit; print('ok')"
```

**4. 建 embedding 服务的环境，并准备好密钥**

```powershell
cd D:\GraphRAG-6
uv venv .venv-embedding
uv pip install --python .venv-embedding\Scripts\python.exe -r requirements-local-embedding.txt
copy .env.example .env
notepad .env
```

> 第 2 条：单独建一个小环境（它要装的东西和前端不一样）。
> 第 3 条：往里装"文本转向量"的工具，**这一步下载最多**。
> 第 4、5 条：复制一份密钥文件，记事本打开，把 `GRAPHRAG_API_KEY=` 后面填上自己的 DeepSeek 密钥，存盘。

### 二、建自己的索引

配置不用手写：`index-template/` 里已经是一份改好的 `settings.yaml` + 13 个提示词
（等价于 `graphrag init` 之后再改好模型、embedding 地址和存储路径）。

**5. 把模板复制成自己的索引目录**

```powershell
xcopy D:\GraphRAG-6\graphrag-workbench\index-template D:\myrag /E /I
mkdir D:\myrag\input
```

> 第 1 条：整个复制成 `D:\myrag`；第 2 条：建个文件夹专门放数据。

**6. 放数据**

把 `.jsonl` 放进 `D:\myrag\input\`，一行一篇文档：

```json
{"id": "mail-001", "title": "主题", "text": "正文……"}
```

> 数据放在别处也行：改 `D:\myrag\settings.yaml` 里 `input_storage.base_dir` 那一行即可。

**7. 索引目录里也放一份密钥**

```powershell
copy D:\GraphRAG-6\.env.example D:\myrag\.env
notepad D:\myrag\.env
```

> 也要填 key。graphrag 只读"settings.yaml 旁边那份 `.env`"，所以索引目录里必须有一份；
> 仓库根那份是给第 8 步的服务读的，内容一样就行。

**8. 起 embedding 服务（新开一个窗口，之后一直别关）**

```powershell
cd D:\GraphRAG-6
Get-Content .env | ForEach-Object { if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim() } }
.\.venv-embedding\Scripts\python.exe scripts\qwen_embedding_server.py
```

> 第 2 条：把 `.env` 里的配置读进这个窗口。第 3 条：启动服务，第一次会自动下载模型权重。
> 验收：浏览器打开 http://127.0.0.1:8000/health ，看到 `{"status":"ok"...}` 就对了。

**9. 建索引（再开一个窗口）**

```powershell
cd D:\GraphRAG-6\graphrag-workbench
uv run python -m graphrag index --root D:\myrag --method standard
```

> `uv run` = 用装好的环境跑；`python -m graphrag index` = 建索引；`--root D:\myrag` = 数据目录。
> `--method standard` = 用大模型抽实体关系（质量好、费 token）；想先省钱试通可换 `--method fast`。
> 跑完 `D:\myrag\` 里会多出 `output\`、`lancedb\`、`cache\`、`logs\`。

### 三、用前端

**10. 启动网页（就在第 9 步那个窗口接着敲）**

```powershell
$env:GRAPHRAG_INDEX = "D:\myrag"
uv run streamlit run app/main.py
```

> 第 1 条：告诉程序"我的索引在哪"（只在当前窗口有效）。第 2 条：启动网页。
> 浏览器打开 http://localhost:8501 ，停止按 `Ctrl + C`。

- **建索引与阶段**：七个阶段、行数、耗时、cache 文件数、产物表格和日志；顶部有"开始建索引"按钮
- **检索对照**：勾方法、问问题、展开"证据链与子图"看命中实体、图路径和子图
- 第一次**只勾 Global**：它只用 DeepSeek 密钥。Local / DRIFT / Basic / 三个自定义方法需要第 8 步的服务一直开着

### 四、不建库，只想用现成的索引

只要三步，索引目录自己准备（含 `settings.yaml`、`prompts/`、`output/`、`lancedb/`、`.env`）：

```powershell
cd D:\GraphRAG-6\graphrag-workbench
uv sync
$env:GRAPHRAG_INDEX = "D:\你的索引目录"
uv run streamlit run app/main.py
```

### 五、卡住了看这四条

1. `uv sync` 报找不到包 → 连不上公司私有源；换网络，或把根 `pyproject.toml` 的 `[[tool.uv.index]]` 换成公网源
2. 网页报 `No module named 'graphrag6_retrieval'` → 第 3 步没成功，回 `graphrag-workbench` 重跑 `uv sync`
3. 提问报 503 / 连接失败 → 第 8 步的服务没起或窗口被关了
4. 界面上出现"某某阶段失败"或"最近一次运行没有正常结束" → 建索引时有步骤挂了（最常见就是第 8 步的服务没起，向量化会失败）；日志在 `<索引目录>\logs\indexing-engine.log`

## 测试

```powershell
cd D:\GraphRAG-6\graphrag-workbench
uv run python -m unittest discover -s tests -t . -v      # 29 个

cd D:\GraphRAG-6\graphrag6-retrieval
uv run --group dev pytest tests                           # 5 个算法测试
```

测试不需要任何外部服务：造临时索引目录验证读取逻辑、喂合成回调事件验证进度折算、
对真实索引只断言"有产物"这类稳定性质（行数会随重建变化，不做硬编码）。
阶段映射表必须覆盖 graphrag 3.1.2 的全部 11 个 workflow，多一个少一个都会让测试失败，
用来防止升级后静默漏阶段。

## 与旧前端的差异

- 删掉了 Azure Blob / 多数据集 `listing.json` / `SessionVariables` 三层抽象，
  索引目录直接由 `GRAPHRAG_INDEX` 指定。
- 缓存从 7 天 TTL 改成 30 秒 TTL + 手动刷新，避免重建索引后一直看到旧数据。
- 建索引进度来自 `graphrag.api.build_index` 的 `WorkflowCallbacks`，阶段产物来自
  `output/*.parquet`、`cache/<workflow>/`、`stats.json` 和 `logs/`。
- 检索算法抽成独立包后，这里只剩界面和编排；算法源码与测试见 `../graphrag6-retrieval`。
