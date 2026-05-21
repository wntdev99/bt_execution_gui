# Copyright 2026 WATT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""GET /api/trees endpoints.

See docs/03_api_protocol.md §2.1.
"""
from __future__ import annotations

from bt_web_bridge.api.common import HTTP_NOT_FOUND, ok, raise_http
from bt_web_bridge.models import TreeDetail, TreeListItem
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/trees', tags=['trees'])


@router.get('')
async def list_trees(request: Request) -> dict:
    """Return all loaded tree manifests as cards."""
    manifests = request.app.state.manifests.get_all()
    items = []
    for tree_id in sorted(manifests):
        m = manifests[tree_id]
        items.append(
            TreeListItem(
                tree_id=m.tree_id,
                display_name=m.display_name,
                description=m.description,
                category=m.category,
                icon=m.icon,
                dangerous=m.dangerous,
                estimated_duration_sec=m.estimated_duration_sec,
                param_count=len(m.params),
            ).model_dump(mode='json')
        )
    return ok(items)


@router.get('/{tree_id}')
async def get_tree(tree_id: str, request: Request) -> dict:
    """Return full manifest detail for a single tree."""
    manifest = request.app.state.manifests.get(tree_id)
    if manifest is None:
        raise_http('TREE_NOT_FOUND', f'unknown tree: {tree_id}', HTTP_NOT_FOUND)

    detail = TreeDetail(
        tree_id=manifest.tree_id,
        display_name=manifest.display_name,
        description=manifest.description,
        category=manifest.category,
        icon=manifest.icon,
        dangerous=manifest.dangerous,
        estimated_duration_sec=manifest.estimated_duration_sec,
        params=manifest.params,
    )
    return ok(detail.model_dump(mode='json'))
