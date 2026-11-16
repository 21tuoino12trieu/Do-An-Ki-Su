# mem0/embeddings/beeflow_embedding.py
from typing import Literal, Optional, Callable, Any, Dict, List, Union
import asyncio
import inspect
import threading

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase
from beegen.configs import *

try:
    # Beeflow / Beegen registry để lấy model embedding
    from beegen.registry.resource_factory import ResourceFactory
except ImportError:
    raise ImportError("beegen is not installed. Please install it and ensure Beeflow/Beegen is available.")


def _run_sync(awaitable):
    """
    Chạy một awaitable trong code đồng bộ.
    - Nếu chưa có event loop: dùng asyncio.run
    - Nếu đang có event loop: tạo thread riêng để tránh lỗi "asyncio.run() in a running loop"
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    box, err = {}, {}

    def _th():
        try:
            box["v"] = asyncio.run(awaitable)
        except Exception as e:
            err["e"] = e

    t = threading.Thread(target=_th, daemon=True)
    t.start()
    t.join()
    if "e" in err:
        raise err["e"]
    return box["v"]


class BeeflowEmbedding(EmbeddingBase):
    """
    Mem0 adapter cho embedding của Beeflow/Beegen.

    Cách dùng:
        from mem0.configs.embeddings.base import BaseEmbedderConfig
        from mem0.embeddings.beeflow_embedding import BeeflowEmbedding

        # Trường hợp 1: truyền tên model của Beeflow (ví dụ: "bge-m3")
        cfg = BaseEmbedderConfig(model="bge-m3")
        embedder = BeeflowEmbedding(cfg)
        vec = embedder.embed("xin chào")         # sync
        # hoặc:
        # vec = await embedder.embed_async("xin chào")

        # Trường hợp 2: truyền callable runner tuỳ biến
        def my_runner(payload):
            # trả về {"embeddings": [[...]]} hoặc [[...]] hoặc [...]
            ...

        cfg = BaseEmbedderConfig(model=my_runner)
        embedder = BeeflowEmbedding(cfg)
    """

    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        super().__init__(config)

        if self.config.model is None:
            raise ValueError("`model` parameter is required")

        # Cho phép:
        # - model là tên (str) để lấy runner từ ModelRegistry
        # - model là callable đã sẵn sàng thực thi embedding
        if isinstance(self.config.model, str):
            self.model_name = self.config.model
            # Thông thường .embedding(name).run sẽ là callable
            self.runner: Callable[..., Any] = ResourceFactory.create(config=EmbeddingConfig.default()).run
        elif callable(self.config.model):
            self.model_name = getattr(self.config.model, "__name__", "custom_callable")
            self.runner = self.config.model
        else:
            raise ValueError("`model` must be either a Beeflow model name (str) or a callable runner")

    # ---------------- Public API ----------------

    def embed(
        self,
        text: str,
        memory_action: Optional[Literal["add", "search", "update"]] = None
    ) -> List[float]:
        """
        Phiên bản ĐỒNG BỘ. Tự động gọi runner dù runner là sync hay async.
        """
        output = self._call_runner_single(text)           # sync-safe (có run_sync)
        return self._normalize_to_vector(output)

    async def embed_async(
        self,
        text: str,
        memory_action: Optional[Literal["add", "search", "update"]] = None
    ) -> List[float]:
        """
        Phiên bản BẤT ĐỒNG BỘ. Nếu runner là sync sẽ trả về trực tiếp,
        nếu runner là async thì await luôn.
        """
        output = await self._call_runner_single_async(text)
        return self._normalize_to_vector(output)

    # ---------------- Internal helpers ----------------

    def _maybe_await_sync(self, res: Any) -> Any:
        """Nếu res là awaitable thì chạy bằng run_sync, ngược lại trả về luôn."""
        if inspect.isawaitable(res):
            return _run_sync(res)
        return res

    async def _maybe_await_async(self, res: Any) -> Any:
        """Nếu res là awaitable thì await, ngược lại trả về luôn."""
        if inspect.isawaitable(res):
            return await res
        return res

    def _call_runner_single(self, text: str) -> Any:
        """
        Gọi runner trong NGỮ CẢNH ĐỒNG BỘ.
        Thử các chữ ký phổ biến:
            1) runner({"texts": [text]})
            2) runner(texts=[text])
            3) runner([text])
            4) runner(text)
        """
        # 1) dict inputs
        try:
            return self._maybe_await_sync(self.runner({"texts": [text]}))
        except TypeError:
            pass
        except Exception:
            pass

        # 2) kwargs
        try:
            return self._maybe_await_sync(self.runner(texts=[text]))
        except TypeError:
            pass
        except Exception:
            pass

        # 3) list
        try:
            return self._maybe_await_sync(self.runner([text]))
        except TypeError:
            pass
        except Exception:
            pass

        # 4) raw string
        return self._maybe_await_sync(self.runner(text))

    async def _call_runner_single_async(self, text: str) -> Any:
        """
        Gọi runner trong NGỮ CẢNH BẤT ĐỒNG BỘ.
        """
        # 1) dict inputs
        try:
            return await self._maybe_await_async(self.runner({"texts": [text]}))
        except TypeError:
            pass
        except Exception:
            pass

        # 2) kwargs
        try:
            return await self._maybe_await_async(self.runner(texts=[text]))
        except TypeError:
            pass
        except Exception:
            pass

        # 3) list
        try:
            return await self._maybe_await_async(self.runner([text]))
        except TypeError:
            pass
        except Exception:
            pass

        # 4) raw string
        return await self._maybe_await_async(self.runner(text))

    @staticmethod
    def _normalize_to_vector(output: Any) -> List[float]:
        """
        Chuẩn hoá các dạng kết quả runner có thể trả về thành list[float].
        Các format được hỗ trợ:
            - {"embeddings": [[...]]}  -> lấy phần tử đầu
            - [[...]]                  -> lấy phần tử đầu
            - [...]                    -> trả về trực tiếp (đã là 1 vector)
        """
        # Case dict với key "embeddings"
        if isinstance(output, dict):
            if "embeddings" in output:
                emb = output["embeddings"]
                if isinstance(emb, list) and len(emb) > 0:
                    if isinstance(emb[0], list):
                        return [float(x) for x in emb[0]]
                    # Một số runner có thể trả về 1 vector 1D
                    if all(isinstance(x, (int, float)) for x in emb):
                        return [float(x) for x in emb]
            # Nếu shape khác, cố gắng tìm một mảng số đầu tiên
            for v in output.values():
                if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                    return [float(x) for x in v]

        # Case list 2D
        if isinstance(output, list) and output:
            if isinstance(output[0], list) and all(isinstance(x, (int, float)) for x in output[0]):
                return [float(x) for x in output[0]]
            # Case 1D
            if all(isinstance(x, (int, float)) for x in output):
                return [float(x) for x in output]

        raise ValueError(
            "Unsupported embedding output shape. Expected {'embeddings': [[...]]} / [[...]] / [...], "
            f"got: {type(output)}"
        )