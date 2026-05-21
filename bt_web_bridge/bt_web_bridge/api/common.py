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
"""Shared API helpers: response envelopes, exception handlers."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


def ok(data: Any) -> dict:
    """Success envelope per docs/03_api_protocol.md §1.3."""
    return {'ok': True, 'data': data}


def err(code: str, message: str, details: Any | None = None) -> dict:
    """Error envelope."""
    payload = {'ok': False, 'error': {'code': code, 'message': message}}
    if details is not None:
        payload['error']['details'] = details
    return payload


def raise_http(code: str, message: str, http_status: int, details: Any | None = None) -> None:
    """Raise an HTTPException with the standard error envelope as detail."""
    raise HTTPException(status_code=http_status, detail=err(code, message, details)['error'])


# Common HTTP status codes mapped to error codes.
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
HTTP_CONFLICT = status.HTTP_409_CONFLICT
HTTP_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
HTTP_INTERNAL = status.HTTP_500_INTERNAL_SERVER_ERROR
HTTP_BAD_GATEWAY = status.HTTP_502_BAD_GATEWAY


def json_response(content: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=content, status_code=status_code)
