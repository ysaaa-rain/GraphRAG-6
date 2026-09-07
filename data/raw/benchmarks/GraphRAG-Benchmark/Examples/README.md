# GraphRAG-Bench Examples

This directory contains example implementations for running inference on the GraphRAG-Bench dataset using various RAG frameworks. Each framework has a dedicated implementation file that generates prediction outputs compatible with our unified evaluation pipeline.

## 🚀 Running Example

Next, we provide detailed instructions on how to use GraphRAG-Bench to evaluate each framework. Specifically, we introduce how to perform index construction and batch inference for each framework. Note that the evaluation code is standardized across all frameworks to ensure fair comparison.

### 1. Indexing and inference

#### a. LightRAG

**We use LightRAG version v1.2.5.**

Before running the above script, you need to modify the source code(LightRAG) to enable extraction of the corresponding context used during generation. Please make the following changes:

1. In `lightrag/operate.py`, update the kg_query method to return the context along with the response:

```python
# Original Code
async def kg_query(...) -> str | AsyncIterator[str]:
  return response

# Modified Code
async def kg_query(...) -> tuple[str, str] | tuple[AsyncIterator[str], str]:
  return response, context
```

2. In `lightrag/lightrag.py`, update the aquery method to receive and return the context when calling kg_query:

```python
# Modified Code
async def aquery(...):
  ...
  if param.mode in ["local", "global", "hybrid"]:
      response, context = await kg_query(...)
  ...
  return response, context

```

Then you can run the following command to indexing and inference

**Note**: Mode can choose:"API" or "ollama". When you choose "ollama" the "llm_base_url" is where your ollama running (default:http://localhost:11434)

```shell
export LLM_API_KEY=your_actual_api_key_here

python run_lightrag.py \
  --subset medical \
  --mode API \
  --base_dir ./Examples/lightrag_workspace \
  --model_name bge-large-en-v1.5 \
  --embed_model bge-base-en \
  --retrieve_topk 5 \
  # --sample 100 \
  --llm_base_url https://api.openai.com/v1

```

#### b. fast-graphrag

Since the original fast-graphrag does not support HuggingFace Embedding, we need to adapt the library accordingly. The detailed adaptation process is as follows:

1. Go to the `fast_graphrag/_llm` directory and create a new file named _hf.py.
   The content of this file is as follows. This code mainly adds support for HuggingFace Embedding:

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import torch
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from fast_graphrag._utils import logger
from fast_graphrag._llm._base import BaseEmbeddingService, NoopAsyncContextManager

@dataclass
class HuggingFaceEmbeddingService(BaseEmbeddingService):
    """Embedding service using HuggingFace models."""

    embedding_dim: Optional[int] = None  # Can be set dynamically if needed
    max_token_size: int = 512
    max_elements_per_request: int = field(default=32)
    tokenizer: Any = None
    model: Any = None

    def __post_init__(self):
        self.embedding_max_requests_concurrent = (
            asyncio.Semaphore(self.max_requests_concurrent) if self.rate_limit_concurrency else NoopAsyncContextManager()
        )
        self.embedding_per_minute_limiter = (
            AsyncLimiter(self.max_requests_per_minute, 60) if self.rate_limit_per_minute else NoopAsyncContextManager()
        )
        self.embedding_per_second_limiter = (
            AsyncLimiter(self.max_requests_per_second, 1) if self.rate_limit_per_second else NoopAsyncContextManager()
        )
        logger.debug("Initialized HuggingFaceEmbeddingService.")

    async def encode(self, texts: list[str], model: Optional[str] = None) -> np.ndarray:
        try:
            logger.debug(f"Getting embedding for texts: {texts}")

            batched_texts = [
                texts[i * self.max_elements_per_request : (i + 1) * self.max_elements_per_request]
                for i in range((len(texts) + self.max_elements_per_request - 1) // self.max_elements_per_request)
            ]
            responses = await asyncio.gather(*[self._embedding_request(batch) for batch in batched_texts])
            embeddings = np.vstack(responses)
            logger.debug(f"Received embedding response: {len(embeddings)} embeddings")
            return embeddings
        except Exception:
            logger.exception("An error occurred during HuggingFace embedding.", exc_info=True)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RuntimeError, torch.cuda.CudaError)),
    )
    async def _embedding_request(self, input_texts: list[str]) -> np.ndarray:
        async with self.embedding_max_requests_concurrent:
            async with self.embedding_per_minute_limiter:
                async with self.embedding_per_second_limiter:
                    logger.debug(f"Embedding request for batch size: {len(input_texts)}")
                    device = (
                        next(self.model.parameters()).device if torch.cuda.is_available()
                        else torch.device("mps") if torch.backends.mps.is_available()
                        else torch.device("cpu")
                    )
                    self.model = self.model.to(device)

                    encoded = self.tokenizer(
                        input_texts, return_tensors="pt", padding=True, truncation=True,  max_length=self.max_token_size
                    ).to(device)

                    with torch.no_grad():
                        outputs = self.model(
                            input_ids=encoded["input_ids"],
                            attention_mask=encoded["attention_mask"]
                        )
                        embeddings = outputs.last_hidden_state.mean(dim=1)

                    if embeddings.dtype == torch.bfloat16:
                        return embeddings.detach().to(torch.float32).cpu().numpy()
                    else:
                        return embeddings.detach().cpu().numpy()

```

2. Then, modify `fast_graphrag/_llm/__init__.py` to include the initialization of the newly added classes.

```python
__all__ = [
    ...
    "HuggingFaceEmbeddingService",
]
...
from ._hf import HuggingFaceEmbeddingService

```

Then you can run the following command to indexing and inference:

```shell
export LLM_API_KEY=your_actual_api_key_here

python run_fast-graphrag.py \
  --subset medical \
  --base_dir ./Examples/fast-graphrag_workspace \
  --model_name gpt-4o-mini \
  --embed_model_path bge-large-en-v1.5 \
  # --sample 100 \
  --llm_base_url https://api.openai.com/v1

```

#### c. hipporag2

**We use hipporag2 version v1.0.0**.

Since the original hipporag2 does not support BGE Embedding models, we need to adapt the library accordingly. The detailed adaptation process is as follows:

1. Go to the `hipporag/embedding_model` directory and create a new file named `BGE.py`.
   The content of this file is as follows. This code mainly adds support for BGE Embedding models:

```python
from copy import deepcopy
from typing import List, Optional

import numpy as np
import torch
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

from ..utils.config_utils import BaseConfig
from ..utils.logging_utils import get_logger
from .base import BaseEmbeddingModel, EmbeddingConfig

logger = get_logger(__name__)

def mean_pooling(token_embeddings, mask):
    """Mean pooling for BGE models"""
    token_embeddings = token_embeddings.masked_fill(~mask[..., None].bool(), 0.)
    sentence_embeddings = token_embeddings.sum(dim=1) / mask.sum(dim=1)[..., None]
    return sentence_embeddings

class BGEEmbeddingModel(BaseEmbeddingModel):
    """BGE (BAAI General Embedding) model implementation"""

    def __init__(self, global_config: Optional[BaseConfig] = None, embedding_model_name: Optional[str] = None) -> None:
        super().__init__(global_config=global_config)

        if embedding_model_name is not None:
            self.embedding_model_name = embedding_model_name
            logger.debug(
                f"Overriding {self.__class__.__name__}'s embedding_model_name with: {self.embedding_model_name}")

        self._init_embedding_config()

        # Initializing the embedding model
        logger.debug(
            f"Initializing {self.__class__.__name__}'s embedding model with params: {self.embedding_config.model_init_params}")

        self.tokenizer = AutoTokenizer.from_pretrained(self.embedding_model_name)
        self.embedding_model = AutoModel.from_pretrained(**self.embedding_config.model_init_params)
        self.embedding_model.eval()
        self.embedding_dim = self.embedding_model.config.hidden_size

    def _init_embedding_config(self) -> None:
        """
        Extract embedding model-specific parameters to init the EmbeddingConfig.

        Returns:
            None
        """

        config_dict = {
            "embedding_model_name": self.embedding_model_name,
            "norm": self.global_config.embedding_return_as_normalized,
            "model_init_params": {
                "pretrained_model_name_or_path": self.embedding_model_name,
                "trust_remote_code": True,
                "torch_dtype": self.global_config.embedding_model_dtype,
                'device_map': "auto",  # added this line to use multiple GPUs
            },
            "encode_params": {
                "max_length": self.global_config.embedding_max_seq_len,
                "instruction": "",
                "batch_size": self.global_config.embedding_batch_size,
                "num_workers": 32
            },
        }

        self.embedding_config = EmbeddingConfig.from_dict(config_dict=config_dict)
        logger.debug(f"Init {self.__class__.__name__}'s embedding_config: {self.embedding_config}")

    def encode(self, texts: List[str], instruction: str = "", **kwargs) -> np.ndarray:
        """
        Encode texts using BGE model with mean pooling.

        Args:
            texts: List of texts to encode
            instruction: Instruction for BGE models (optional)
            **kwargs: Additional parameters

        Returns:
            numpy.ndarray: Encoded embeddings
        """
        if instruction:
            texts = [f"{instruction}{text}" for text in texts]

        encoded_input = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.embedding_config.encode_params["max_length"],
            return_tensors='pt'
        )

        with torch.no_grad():
            model_output = self.embedding_model(**encoded_input)
            sentence_embeddings = mean_pooling(model_output.last_hidden_state, encoded_input['attention_mask'])

        if self.embedding_config.norm:
            sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)

        return sentence_embeddings.cpu().numpy()

    def encode_queries(self, queries: List[str], **kwargs) -> np.ndarray:
        """Encode queries using BGE model"""
        return self.encode(queries, instruction="Represent this sentence for searching relevant passages: ", **kwargs)

    def encode_corpus(self, corpus: List[str], **kwargs) -> np.ndarray:
        """Encode corpus using BGE model"""
        return self.encode(corpus, instruction="Represent this sentence for searching relevant passages: ", **kwargs)
```

2. Then, modify `hipporag/embedding_model/__init__.py` to include the initialization of the newly added BGE class:

```python
from .Contriever import ContrieverModel
from .base import EmbeddingConfig, BaseEmbeddingModel
from .GritLM import GritLMEmbeddingModel
from .NVEmbedV2 import NVEmbedV2EmbeddingModel
from .OpenAI import OpenAIEmbeddingModel
from .BGE import BGEEmbeddingModel

from ..utils.logging_utils import get_logger

logger = get_logger(__name__)


def _get_embedding_model_class(embedding_model_name: str = "nvidia/NV-Embed-v2"):
    if "GritLM" in embedding_model_name:
        return GritLMEmbeddingModel
    elif "NV-Embed-v2" in embedding_model_name:
        return NVEmbedV2EmbeddingModel
    elif "contriever" in embedding_model_name:
        return ContrieverModel
    elif "text-embedding" in embedding_model_name:
        return OpenAIEmbeddingModel
    elif "bge" in embedding_model_name.lower():
        return BGEEmbeddingModel
    assert False, f"Unknown embedding model name: {embedding_model_name}"
```

Then you can run the following command to indexing and inference:

**Note**: Mode can choose:"API" or "ollama". When you choose "ollama" the "llm_base_url" is where your is ollama running (default:http://localhost:11434)

```shell
export OPENAI_API_KEY=your_actual_api_key_here

python run_hipporag2.py \
  --subset medical \
  --mode API\
  --base_dir ./Examples/hipporag2_workspace \
  --model_name gpt-4o-mini \
  --embed_model_path /path/to/your/local/bge-large-en-v1.5 \
  # --sample 100 \
  --llm_base_url https://api.openai.com/v1
```

#### d. DIGIMON
DIGIMON is a unified framework that integrates multiple GraphRAG frameworks: [DIGIMON: Deep Analysis of Graph-Based Retrieval-Augmented Generation (RAG) Systems](https://github.com/JayLZhou/GraphRAG)
1. Move `run_digimon.py` into the corresponding DIGIMON project.  
2. Modify the related config files according to the DIGIMON instructions.  
3. Run the following command:

```bash
python run_digimon.py \
  --subset novel \
  --option ./Option/Method/HippoRAG.yaml \
  --output_dir ./results/test \
  # --sample 100
```

We will continue updating other GraphRAG frameworks as much as possible. If you wish to integrate a different framework, you can refer to the structure of our result format. As long as your returned output matches the following fields, the evaluation code will run successfully:

```json
{
  "id": q["id"],
  "question": q["question"],
  "source": corpus_name,
  "context": List[str],
  "evidence": q["evidence"],
  "question_type": q["question_type"],
  "generated_answer": predicted_answer,
  "ground_truth": q["answer"]
}

```



