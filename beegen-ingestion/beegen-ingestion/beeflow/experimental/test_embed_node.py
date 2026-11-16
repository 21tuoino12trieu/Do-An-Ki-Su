from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.primitives.ai.embedding_node import EmbeddingNode
from beegen.embeddings.vllm_embedding import EmbeddingResponse
from beegen.configs.models.embedding_config import EmbeddingConfig
from beeflow.nodes.base_node import INPUT, OUTPUT
from typing import Union, List 
import asyncio
class Embedding:
    def __init__(self):
        self.emb_node=EmbeddingNode(
            name="emb0",
            resource_key="bge-m3",
            inputs=INPUT,
            outputs=OUTPUT,
            status_message="bố mày embedding xong rồi, dkm!",
            stream=True
        )

        self.indexer = WorkflowIndexer(name="workflow01").add_node(self.emb_node).build()
        # config = EmbeddingConfig.default
    async def embed(self, text: Union[str, List[str]]):

        state = WorkflowState(
            indexer=self.indexer, 
            inputs={
                "texts": text
            }
        )

        outputs = await self.emb_node.run(state=state)
        # print(self.emb_node.trace_data(state, None))
        return outputs 
    

async def main():
    embed_node = Embedding()
    texts = ["Tôi không phải fan phim kinh dị nhưng tôi thích phim khoa học viễn tưởng",
              "Tôi đang hơi mệt, xem cái gì nhẹ nhàng thôi. Hoặc có thể chuyển sang xem series cũng được."]
    
    outputs: EmbeddingResponse = await embed_node.embed(texts)
    # print(outputs)
    # print(f"object: {outputs.object}")
    # print(f"model: {outputs.model}")
    # print(f"usage: {outputs.usage}")
    # embedding_datas = outputs.data
    # for data in embedding_datas:
    #     print("----------------------------------")
    #     print(data.index)
    #     print(data.object)
    #     print(f"vector length: {len(data.embedding)}")

    for key, value in outputs.items():
        print(key) 
        if isinstance(value, list):
            print(f"list length: {len(value)}")
        else:
            print(value)

    for item in outputs["embeddings"]:
        print(len(item))



if __name__ == "__main__":
    asyncio.run(main())