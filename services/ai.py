import httpx
from typing import List
from services.config import ConfigCenter


async def describe_image_base64(base64_image: str, detail: str = "high") -> str:
    """
    传入base64图片和文本提示，返回图片描述文本。
    """
    OAI_API_URL = await ConfigCenter.get("AI_VISION_API_URL")
    VISION_MODEL = await ConfigCenter.get("AI_VISION_MODEL")
    API_KEY = await ConfigCenter.get("AI_VISION_API_KEY")
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "user", "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": detail
                    }
                },
                {
                    "type": "text",
                    "text": "描述这个图片"
                }
            ]}
        ]
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(OAI_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"]
    except httpx.ReadTimeout:
        return "请求超时，请稍后重试。"
    except Exception as e:
        return f"请求失败: {str(e)}"


async def get_text_embedding(text: str) -> List[float]:
    """
    传入文本，返回嵌入向量。
    """
    OAI_API_URL = await ConfigCenter.get("AI_EMBED_API_URL")
    EMBED_MODEL = await ConfigCenter.get("AI_EMBED_MODEL")
    API_KEY = await ConfigCenter.get("AI_EMBED_API_KEY")
    payload = {
        "model": EMBED_MODEL,
        "input": text
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        if OAI_API_URL.endswith("chat/completions"):
            url = OAI_API_URL.replace("chat/completions", "embeddings")
        else:
            url = OAI_API_URL
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()
        return result["data"][0]["embedding"]


async def rerank_texts(query: str, documents: List[str]) -> List[float]:
    """调用重排序模型，为一组文档返回得分。未配置时返回空列表。"""
    if not documents:
        return []

    api_url = await ConfigCenter.get("AI_RERANK_API_URL")
    model = await ConfigCenter.get("AI_RERANK_MODEL")
    api_key = await ConfigCenter.get("AI_RERANK_API_KEY")

    if not api_url or not model or not api_key:
        return []

    payload = {
        "model": model,
        "query": query,
        "documents": documents,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(api_url, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return []
        data = resp.json()
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list):
                scores = []
                for item in results:
                    if isinstance(item, dict) and "score" in item:
                        try:
                            scores.append(float(item["score"]))
                        except (TypeError, ValueError):
                            scores.append(0.0)
                return scores
        return []
