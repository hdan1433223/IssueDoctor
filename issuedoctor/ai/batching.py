import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatchItem:
    issue_number: int
    title: str
    body: str
    metadata: dict = field(default_factory=dict)

    @property
    def character_count(self) -> int:
        metadata_characters = (
            len(json.dumps(self.metadata, ensure_ascii=False)) if self.metadata else 0
        )
        return len(self.title) + len(self.body) + metadata_characters


def build_batches(
    items: list[BatchItem],
    *,
    maximum_items: int,
    maximum_characters: int,
) -> list[list[BatchItem]]:
    batches: list[list[BatchItem]] = []
    current: list[BatchItem] = []
    characters = 0
    for item in items:
        if current and (
            len(current) >= maximum_items
            or characters + item.character_count > maximum_characters
        ):
            batches.append(current)
            current = []
            characters = 0
        current.append(item)
        characters += item.character_count
    if current:
        batches.append(current)
    return batches
