# GraphRAG LLM 组件

本包统一封装 completion、embedding、重试、限流、缓存、token 统计和模型指标接口。项目将 DeepSeek 用于生成/抽取，将本地 Qwen 服务用于 embedding，并在 GraphRAG 与 Vector 对照中复用相同配置。

## 开源来源

本组件源自 [Microsoft GraphRAG](https://github.com/microsoft/graphrag)，沿用仓库根目录的 MIT 许可证，源码版权声明保留。
