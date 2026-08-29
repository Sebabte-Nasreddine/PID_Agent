# app/core/llm_client.py
import json
import base64
from json import JSONDecodeError

import ollama
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from pydantic import BaseModel

from app.config import settings


_token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default"
)

_azure_client = OpenAI(
    base_url=settings.azure_openai_endpoint,
    api_key=_token_provider,
)


def call_cloud_llm_structured(prompt: str, schema: type[BaseModel]) -> BaseModel:
    response = _azure_client.responses.create(
        model=settings.azure_openai_deployment,
        input=[{"role": "user", "content": prompt}],
        text={
            "format": {
                "type": "json_schema",
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            }
        },
    )
    return schema.model_validate_json(response.output_text)


def call_cloud_llm_structured_vision(prompt: str, image_b64: str, schema: type[BaseModel]) -> BaseModel:
    response = _azure_client.responses.create(
        model=settings.azure_openai_deployment,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
            ],
        }],
        text={
            "format": {
                "type": "json_schema",
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            }
        },
    )
    return schema.model_validate_json(response.output_text)


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_local_llm_structured(prompt: str, image_b64: str, schema: type[BaseModel]) -> BaseModel:
    response = ollama.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt, "images": [image_b64]}],
        format=schema.model_json_schema(),
        options={"temperature": 0.0},
    )
    raw_content = response["message"]["content"]

    try:
        data = json.loads(raw_content)
    except JSONDecodeError as e:
        raise JSONDecodeError(f"Ollama returned invalid JSON: {e.msg}", e.doc, e.pos) from e

    return schema.model_validate(data)