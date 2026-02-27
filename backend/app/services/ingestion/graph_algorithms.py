import math
from collections import defaultdict, deque
from typing import Optional


def enforce_dag_on_map(
    edge_map: dict[tuple[str, str], dict],
    prereq_rel_types: set[str],
    *,
    logger=None,
) -> int:
    """Detect and break cycles in prerequisite subgraph (in-place on edge_map)."""
    adj: dict[str, list[tuple[str, tuple[str, str]]]] = defaultdict(list)
    for key, data in edge_map.items():
        if data["relation_type"] in prereq_rel_types:
            adj[data["source"]].append((data["target"], key))

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    keys_to_break: list[tuple[str, str]] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        for neighbor, edge_key in adj.get(node, []):
            if color[neighbor] == GRAY:
                keys_to_break.append(edge_key)
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        color[node] = BLACK

    all_nodes: set[str] = set()
    for data in edge_map.values():
        if data["relation_type"] in prereq_rel_types:
            all_nodes.add(data["source"])
            all_nodes.add(data["target"])

    for node in all_nodes:
        if color[node] == WHITE:
            dfs(node)

    for key in keys_to_break:
        if key in edge_map:
            edge_map[key]["relation_type"] = "RELATED_TO"
            edge_map[key]["dir_forward"] = 0.5
            edge_map[key]["dir_backward"] = 0.5
            if logger:
                logger.debug("[DAG] Broke cycle edge: %s -> %s", key[0], key[1])

    return len(keys_to_break)


def compute_topo_order_from_map(
    edge_map: dict[tuple[str, str], dict],
    concepts: set[str],
) -> dict[str, int]:
    """Compute topological ordering from directed prerequisite edges."""
    directed_types = {"REQUIRES", "ENABLES", "DERIVES_FROM"}
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {c: 0 for c in concepts}

    for data in edge_map.values():
        if data["relation_type"] in directed_types:
            adj[data["source"]].append(data["target"])
            in_degree.setdefault(data["target"], 0)
            in_degree[data["target"]] = in_degree.get(data["target"], 0) + 1

    queue = deque([c for c in concepts if in_degree.get(c, 0) == 0])
    order: dict[str, int] = {}
    idx = 0
    while queue:
        node = queue.popleft()
        order[node] = idx
        idx += 1
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    for concept in concepts:
        if concept not in order:
            order[concept] = idx

    return order


def compute_qhat_vectors(evidence) -> dict[str, dict[str, float]]:
    """Compute sparse q-hat vectors: concept_id -> {chunk_id: weighted_score}."""
    qhat: dict[str, dict[str, float]] = defaultdict(dict)

    for item in evidence:
        chunk_key = str(item.chunk_id)
        weight = item.weight * (item.quality_score or 0.5)

        if chunk_key in qhat[item.concept_id]:
            qhat[item.concept_id][chunk_key] += weight
        else:
            qhat[item.concept_id][chunk_key] = weight

    return dict(qhat)


def cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    common_keys = set(vec1.keys()) & set(vec2.keys())
    if not common_keys:
        return 0.0

    dot_product = sum(vec1[key] * vec2[key] for key in common_keys)
    mag1 = math.sqrt(sum(value ** 2 for value in vec1.values()))
    mag2 = math.sqrt(sum(value ** 2 for value in vec2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


def ppmi_score(
    vec1: dict[str, float],
    vec2: dict[str, float],
    count1: int,
    count2: int,
    total_chunks: int,
    min_cooccurrence: int = 1,
) -> float:
    """Compute normalized Positive PMI in [0, 1] for concept co-occurrence."""
    common_chunks = set(vec1.keys()) & set(vec2.keys())
    co_occurrence = len(common_chunks)

    if co_occurrence < max(1, min_cooccurrence):
        return 0.0

    p_c1 = count1 / total_chunks
    p_c2 = count2 / total_chunks
    p_c1_c2 = co_occurrence / total_chunks

    if p_c1 == 0 or p_c2 == 0:
        return 0.0

    pmi = math.log2(p_c1_c2 / (p_c1 * p_c2))
    ppmi = max(0.0, pmi)

    max_possible_pmi = -math.log2(max(p_c1, p_c2))
    if max_possible_pmi > 0:
        return min(1.0, ppmi / max_possible_pmi)

    return ppmi


def compute_direction(
    c1: str,
    c2: str,
    evidence,
    prereq_lookup: Optional[dict[tuple[str, str], int]] = None,
) -> tuple[float, float]:
    """Compute directional prior between two concepts from document order + prereq hints."""
    c1_positions = [
        (item.position_index, item.weight * (item.quality_score or 0.5))
        for item in evidence
        if item.concept_id == c1 and item.position_index is not None
    ]
    c2_positions = [
        (item.position_index, item.weight * (item.quality_score or 0.5))
        for item in evidence
        if item.concept_id == c2 and item.position_index is not None
    ]

    if not c1_positions or not c2_positions:
        dir_forward = 0.5
        dir_backward = 0.5
    else:
        forward = 0.0
        backward = 0.0
        for pos1, weight1 in c1_positions:
            for pos2, weight2 in c2_positions:
                if pos1 == pos2:
                    continue
                pair_weight = weight1 * weight2
                if pos1 < pos2:
                    forward += pair_weight
                else:
                    backward += pair_weight

        total = forward + backward
        if total == 0:
            dir_forward = 0.5
            dir_backward = 0.5
        else:
            ratio = (forward - backward) / total
            dir_forward = 0.5 + ratio * 0.4
            dir_forward = min(0.95, max(0.05, dir_forward))
            dir_backward = 1.0 - dir_forward

    if prereq_lookup:
        forward_support = prereq_lookup.get((c1, c2), 0)
        backward_support = prereq_lookup.get((c2, c1), 0)
        total_support = forward_support + backward_support

        if total_support > 0:
            bias = (forward_support - backward_support) / total_support
            boost = min(0.2, 0.05 * total_support)
            dir_forward = dir_forward + boost * bias
            dir_forward = min(0.95, max(0.05, dir_forward))
            dir_backward = 1.0 - dir_forward

    return round(dir_forward, 3), round(dir_backward, 3)
