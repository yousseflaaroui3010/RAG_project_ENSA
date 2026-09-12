"""Generic OpenAPI 3.1 response validator for docs/phase2/openapi.yaml.

ST-52's exit gate says CI fails on schema drift. The Sev1 finding on the
rule-5 review of ST-51/ST-52 is that this never actually held: `app.py`
serves the yaml file itself as `/openapi.json` (no route declares a
response model FastAPI could generate one from), so the existing "served
equals contract" test compares the file to itself and can never fail no
matter how far a real response drifts from what is documented. Fourteen
deliberate breaks were tried against the branch's suite and eleven stayed
green, including renaming a response field, dropping three required ones,
and moving four documented error codes to undocumented ones.

This module is the real check: every response `ContractClient` receives is
validated against the schema documented for its (path, method, status) in
the signed contract --

* the status code itself must be one this operation documents at all;
* every property the schema declares for that response must be present
  (not only the ones listed under `required` -- see `_flatten_object`'s
  docstring for why a bare required-list is not enough here);
* no property the schema does not name may appear;
* nested types, `enum`, `items`, and nullable (`type: [X, "null"]`) are
  checked recursively, resolving `$ref` and merging `allOf` as OpenAPI
  actually composes them.

No jsonschema dependency (pyproject.toml does not declare one, and this
contract only uses $ref / allOf / type / enum / items / required -- a
hand-rolled resolver covers all of it in one auditable file, which is
cheaper than a scout report and a new pin for a library that would spend
most of its surface unused here).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi.testclient import TestClient


def _resolve(schema: dict, root: dict) -> dict:
    """Follow one `$ref`. Only local (`#/...`) refs exist in this contract."""
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/"), f"only local $ref is supported, got {ref!r}"
        node: Any = root
        for part in ref[2:].split("/"):
            node = node[part]
        return node
    return schema


def _types(schema: dict) -> list[str] | None:
    declared = schema.get("type")
    if declared is None:
        return None
    return declared if isinstance(declared, list) else [declared]


def _check_type(value: Any, type_name: str) -> bool:
    # bool is an int subclass in Python; JSON Schema treats them as
    # disjoint, so `isinstance(True, int)` must not pass an "integer" check.
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "null":
        return value is None
    raise AssertionError(f"unsupported json schema type in contract: {type_name!r}")


def _flatten_object(schema: dict, root: dict) -> dict:
    """Every declared property for an object schema, merged across `allOf`.

    WorkspaceDetail, SyncRunDetail and EvalRunDetail are all `allOf:
    [Base, {extra fields}]`. Validating a value against each branch
    SEPARATELY (the naive recursive approach) breaks the closed-property
    check: the base branch alone does not know about the extension's
    fields and would flag them as undocumented, and vice versa. So this
    flattens every `allOf` branch's `properties` into one dict first, and
    the caller validates against the merged shape exactly once."""
    schema = _resolve(schema, root)
    properties: dict = {}
    for sub in schema.get("allOf", ()):
        properties.update(_flatten_object(sub, root))
    properties.update(schema.get("properties", {}))
    return properties


def validate_value(value: Any, schema: dict, root: dict, *, path: str) -> None:
    schema = _resolve(schema, root)
    types = _types(schema)
    if types is not None:
        assert any(_check_type(value, candidate) for candidate in types), (
            f"{path}: expected type {types}, got {value!r} ({type(value).__name__})"
        )
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} is not one of {schema['enum']}"
    if isinstance(value, dict):
        properties = _flatten_object(schema, root)
        extra = set(value) - set(properties)
        assert not extra, f"{path}: response carries undocumented field(s) {sorted(extra)}"
        # CLOSED, not just "required" honoured: every field this response
        # schema names is expected to always be present, matching how the
        # app actually builds these dicts (a nullable field is still a KEY
        # with a null value, never an absent key). This is what turns
        # "dropping page_count" red -- DocumentEntry.page_count is
        # nullable but not in `required`, so a bare required-list check
        # would miss its silent removal entirely.
        missing = set(properties) - set(value)
        assert not missing, f"{path}: response is missing documented field(s) {sorted(missing)}"
        for key, item in value.items():
            validate_value(item, properties[key], root, path=f"{path}.{key}")
    elif isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema is not None:
            for index, item in enumerate(value):
                validate_value(item, items_schema, root, path=f"{path}[{index}]")


def _path_pattern(path_template: str) -> re.Pattern[str]:
    """`/api/v1/workspaces/{workspace_id}` -> a regex matching the concrete
    request path, one `{param}` standing for exactly one path segment."""
    escaped = re.escape(path_template)
    filled = re.sub(r"\\\{[^}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{filled}$")


def find_operation(contract: dict, method: str, path: str) -> tuple[str, dict] | None:
    """The (path template, operation object) documenting this request, or
    None if the contract has nothing at this path at all."""
    for path_template, path_item in contract["paths"].items():
        if _path_pattern(path_template).match(path):
            operation = path_item.get(method.lower())
            if operation is not None:
                return path_template, operation
    return None


def validate_response(
    contract: dict, method: str, path: str, response: httpx.Response
) -> None:
    found = find_operation(contract, method, path)
    assert found is not None, (
        f"{method} {path} is not documented in docs/phase2/openapi.yaml at all"
    )
    path_template, operation = found
    responses = operation["responses"]
    status = str(response.status_code)
    assert status in responses, (
        f"{method} {path_template} returned {status}, which the contract does not "
        f"document for this operation (documented statuses: {sorted(responses)})"
    )
    response_spec = _resolve(responses[status], contract)
    content = response_spec.get("content")
    if not content:
        return
    schema = content["application/json"]["schema"]
    validate_value(
        response.json(), schema, contract, path=f"{method} {path_template} {status}"
    )


class ContractClient(TestClient):
    """A `TestClient` that checks every `/api/v1` response against the
    signed contract as it comes back, turning every test that uses it into
    a contract test with no per-call changes.

    Overriding `request()` rather than `get`/`post`/`patch`/`delete`
    individually: httpx.Client implements all four as thin wrappers that
    call `self.request(...)`, so this one seam catches every verb this
    test suite uses."""

    def __init__(self, app: Any, *args: Any, contract: dict, **kwargs: Any) -> None:
        super().__init__(app, *args, **kwargs)
        self._contract = contract

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> httpx.Response:
        response = super().request(method, url, *args, **kwargs)
        path = httpx.URL(str(url)).path
        if path.startswith("/api/v1"):
            validate_response(self._contract, method, path, response)
        return response
