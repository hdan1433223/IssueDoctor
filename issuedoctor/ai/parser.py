import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from issuedoctor.errors import IssueDoctorError

SchemaT = TypeVar("SchemaT", bound=BaseModel)
FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
TRAILING_COMMA = re.compile(r",\s*([}\]])")


def parse_json_response(content: str, schema: type[SchemaT]) -> SchemaT:
    candidate = _clean_candidate(content)
    try:
        payload = json.loads(candidate)
        return schema.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise IssueDoctorError("LLM_INVALID_JSON", "LLM 返回的 JSON 不符合约定格式") from exc


def parse_list_response(
    content: str,
    container_schema: type[SchemaT],
    item_schema: type[BaseModel],
    list_key: str,
) -> SchemaT:
    """Validate list items independently and salvage complete items from truncated JSON."""
    candidate = _clean_candidate(content)
    try:
        payload = json.loads(candidate)
        raw_items = payload.get(list_key, []) if isinstance(payload, dict) else []
    except json.JSONDecodeError:
        raw_items = _recover_array_items(candidate, list_key)

    valid_items = []
    for raw_item in raw_items:
        try:
            valid_items.append(item_schema.model_validate(raw_item))
        except ValidationError:
            continue
    if not valid_items:
        raise IssueDoctorError("LLM_INVALID_JSON", "LLM 返回内容中没有可用的结构化条目")
    return container_schema.model_validate({list_key: valid_items})


def _clean_candidate(content: str) -> str:
    candidate = content.strip()
    fenced = FENCED_JSON.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    starts = [index for index in (candidate.find("{"), candidate.find("[")) if index >= 0]
    candidate = candidate[min(starts) if starts else 0 :]
    if candidate.startswith("{"):
        end = candidate.rfind("}")
        candidate = candidate[: end + 1] if end >= 0 else candidate
    return TRAILING_COMMA.sub(r"\1", candidate)


def _recover_array_items(candidate: str, list_key: str) -> list[dict]:
    match = re.search(rf'"{re.escape(list_key)}"\s*:\s*\[', candidate)
    if not match:
        return []
    decoder = json.JSONDecoder()
    index = match.end()
    items: list[dict] = []
    while index < len(candidate):
        while index < len(candidate) and candidate[index] in " \r\n\t,":
            index += 1
        if index >= len(candidate) or candidate[index] == "]":
            break
        try:
            value, index = decoder.raw_decode(candidate, index)
        except json.JSONDecodeError:
            break
        if isinstance(value, dict):
            items.append(value)
    return items
