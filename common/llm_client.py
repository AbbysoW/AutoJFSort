import os
import threading
import json
import logging
import textwrap
from time import monotonic
from typing import Any, TypeVar, Type
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError
from pydantic import BaseModel

from config import settings


logger = logging.getLogger(__name__)


T = TypeVar("T", bound=BaseModel)

class LLMClient:
    _client: OpenAI | None = None
    _lock = threading.Lock()

    _json_notificator = textwrap.dedent(f"""\
            Возвращай ответ в структуре JSON.
            JSON должен соответствовать следующей схеме:
        """)


    @classmethod
    def _get_client(cls) -> OpenAI:
        with cls._lock:
            if cls._client is None:
                cls._client = OpenAI(
                    base_url="https://api.deepseek.com",
                    api_key=settings.llm_api_key,
                )
            return cls._client

    @classmethod
    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
    )
    def send_request(cls, system_prompt: str, user_content: str, output_format: Any | None = None, temperature: float = 0.5):
        started_at = monotonic()
        logger.debug("LLM request started: prompt_length=%s, input_length=%s, structured=%s, temperature=%s", len(system_prompt), len(user_content), output_format is not None, temperature)
        try:
            request = {
                "model": "deepseek-v4-flash",
                "messages": [
                    {"role": "user", "content": user_content},
                ],
                "temperature": temperature,
            }
            if output_format is None or type(output_format) is str:
                request["messages"].insert(0, {"role": "system", "content": system_prompt})
                response = cls._get_client().chat.completions.create(**request)
                result = response.choices[0].message.content
            else:
                request["messages"].insert(0, {"role": "system", "content":
                                            system_prompt + cls._json_notificator + cls.get_schema_prompt(output_format)})
                response = cls._get_client().chat.completions.create(
                    response_format={"type": "json_object"},
                    **request,
                )
                result = cls.parse_response(response.choices[0].message.content, output_format)

            output_length = len(response.choices[0].message.content or "")
            logger.info("LLM request completed: output_length=%s, duration_ms=%s", output_length, round((monotonic() - started_at) * 1000))
            return result
        except RateLimitError as e:
            logger.warning("LLM rate limit: error=%s", e)
            raise
        except APIConnectionError as e:
            logger.error("LLM connection failed: error=%s", e, exc_info=True)
            raise
        except APITimeoutError as e:
            logger.error("LLM request timed out: error=%s", e, exc_info=True)
            raise
        except Exception:
            logger.exception("LLM request failed: structured=%s", output_format is not None)
            raise

    @staticmethod
    def get_schema_prompt(model: type[BaseModel]) -> str:
        return json.dumps(
            model.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def parse_response(content: str, model: Type[T]) -> T:
        return model.model_validate_json(content)