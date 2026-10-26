from dataclasses import replace

from issuedoctor.embedding.similarity import SimilarityCandidate


def assign_clusters(candidates: list[SimilarityCandidate]) -> list[SimilarityCandidate]:
    parent: dict[int, int] = {}

    def find(value: int) -> int:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for candidate in candidates:
        union(candidate.issue_a, candidate.issue_b)
    roots = sorted({find(value) for value in parent})
    cluster_ids = {root: f"cluster-{index + 1}" for index, root in enumerate(roots)}
    return [
        replace(candidate, cluster_id=cluster_ids[find(candidate.issue_a)])
        for candidate in candidates
    ]

