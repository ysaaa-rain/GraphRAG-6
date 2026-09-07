### 2. Evaluation

**Note**: Mode can choose:"API" or "ollama". When you choose "ollama" the "llm_base_url" is where your ollama running (default:http://localhost:11434)

#### a. Generation

Evaluate the quality of generated answers from GraphRAG frameworks using multiple metrics tailored for different question types.

**Metrics per Question Type:**
- **Fact Retrieval**: ROUGE-L score, Answer Correctness
- **Complex Reasoning**: ROUGE-L score, Answer Correctness  
- **Contextual Summarize**: Answer Correctness, Coverage Score
- **Creative Generation**: Answer Correctness, Coverage Score, Faithfulness

```shell
export LLM_API_KEY=your_actual_api_key_here

python -m Evaluation.generation_eval \
  --mode API \
  --model gpt-4o-mini \
  --base_url https://api.openai.com/v1 \
  --embedding_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/lightrag.json \
  --output_file ./results/evaluation_results.json \
  # --detailed_output
```

#### b. Retrieval

Evaluate the quality of retrieved contexts from GraphRAG frameworks using context relevance and recall metrics.

**Metrics:**
- **Context Relevancy**: Measures how relevant the retrieved contexts are to the question
- **Evidence Recall**: Measures how well the retrieved contexts cover the ground truth evidence

```shell
export LLM_API_KEY=your_actual_api_key_here

python -m Evaluation.retrieval_eval \
  --mode API \
  --model gpt-4o-mini \
  --base_url https://api.openai.com/v1 \
  --embedding_model BAAI/bge-large-en-v1.5 \
  --data_file ./results/lightrag.json \
  --output_file ./results/evaluation_results.json \
  # --detailed_output
```

#### c. Indexing

Evaluate the indexing quality of knowledge graphs constructed by different GraphRAG frameworks. This tool analyzes graph structure metrics including density, connectivity, clustering coefficients, and entity/relationship distributions.

```shell
python -m Evaluation.indexing_eval \
  --framework lightrag \
  --base_path ./Examples/lightrag_workspace \
  --folder_name graph_store \
  --output ./results/indexing_metrics.txt
```

**Supported frameworks:**
- `microsoft_graphrag`: Microsoft GraphRAG (uses entities.parquet and relationships.parquet)
- `lightrag`: LightRAG (uses graph_chunk_entity_relation.graphml)
- `fast_graphrag`: Fast-GraphRAG (uses graph_igraph_data.pklz)
- `hipporag2`: HippoRAG2 (uses graph.pickle)
- `graphml`: Generic GraphML format graph files