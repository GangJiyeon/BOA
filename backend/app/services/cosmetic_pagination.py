"""동일 정렬 조건 안에서만 5개씩 조회. 결과 변경 시 이전 위치를 재사용하지 않는다."""
import hashlib
import json

from app.schemas.cosmetic import RankingTieGroup


class StaleRecommendationError(ValueError):
    pass


class PaginationInputError(ValueError):
    pass


def paginate_ties(request, ordered, context):
    payload = {
        "contract": "cosmetic-ties-v1",
        "request": request.model_dump(exclude={"tie_group", "tie_offset", "snapshot_token"}),
        "context": context,
        "candidates": [r.product.model_dump() | {
            "groups": r.group_count, "preferred": r.priority_matched, "ties": r.tie_count,
        } for r in ordered],
    }
    token = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    if request.snapshot_token is not None and request.snapshot_token != token:
        raise StaleRecommendationError("추천 조건이나 데이터가 변경됐습니다. 추천 제품을 다시 조회해 주세요.")
    groups = {}
    start = 0
    while start < len(ordered):
        size = ordered[start].tie_count
        groups[f"g-{start + 1}"] = ordered[start:start + size]
        start += size
    if request.tie_group is not None:
        rows = groups.get(request.tie_group)
        if rows is None or request.tie_offset >= len(rows):
            raise PaginationInputError("유효하지 않은 동점 그룹 또는 조회 위치입니다.")
        selections = [(request.tie_group, rows[request.tie_offset:request.tie_offset + 5], request.tie_offset)]
    else:
        selections = []
        remaining = 5
        for key, rows in groups.items():
            if not remaining:
                break
            selected = rows[:remaining]
            selections.append((key, selected, 0))
            remaining -= len(selected)
    items, metadata = [], []
    for key, rows, offset in selections:
        end = offset + len(rows)
        metadata.append(RankingTieGroup(key=key, total=len(groups[key]),
                                       next_offset=end if end < len(groups[key]) else None))
        items.extend(r.product.model_copy(update={
            "rank": r.rank, "ranking_tie_count": r.tie_count, "ranking_group": key,
            "matched_group_count": r.group_count, "priority_matched": r.priority_matched,
        }) for r in rows)
    return items, metadata, token
