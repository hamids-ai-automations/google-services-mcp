"""Regenerate ``docs/tools.md`` from the registered :class:`ToolSpec` metadata.

Usage (from the repository root, with the project virtualenv active):

    python scripts/gen_tools_doc.py

The script builds the real server, so the table cannot drift from the code: adding a
tool changes the docs automatically, and a broken schema fails the build here first.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google_services_mcp.config import Settings  # noqa: E402
from google_services_mcp.permissions import Operation, PermissionPolicy  # noqa: E402
from google_services_mcp.server import build_server  # noqa: E402

OUTPUT = ROOT / "docs" / "tools.md"

INTRO = """# Tool reference

Every tool is gated by `PermissionPolicy` before the Google call and audited afterwards. `Policy` is the key that must
be enabled under `permissions.services.<service>.`; `Destructive` means `confirm: true` is required; `Idempotent` is
used for retry/back-off decisions. `Available now` reflects the default configuration shipped in
`config/config.example.yaml` (read-only mode).

Regenerate with `python scripts/gen_tools_doc.py`.
"""


def _cell(value: str) -> str:
    return value.replace("|", "\\|").strip()


def render(settings: Settings) -> str:
    server = build_server(settings)
    specs = sorted(server.gsmcp_specs, key=lambda spec: (spec.service, spec.name))
    policy = PermissionPolicy(settings)

    lines: list[str] = [INTRO, f"Registered tools: **{len(specs)}**.", ""]

    by_service: dict[str, list] = {}
    for spec in specs:
        by_service.setdefault(spec.service, []).append(spec)

    for service in sorted(by_service):
        lines.append(f"## {service.title()}")
        lines.append("")
        lines.append("| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for spec in by_service[service]:
            allowed = policy.check(spec)[0]
            lines.append(
                "| `{name}` | `{key}` | {op} | {destructive} | {idem} | {avail} | {desc} |".format(
                    name=spec.name,
                    key=spec.policy_key,
                    op=spec.operation.value,
                    destructive="yes" if spec.destructive or spec.operation is Operation.DESTRUCTIVE else "—",
                    idem="yes" if spec.idempotent else "no",
                    avail="yes" if allowed else "no",
                    desc=_cell(spec.description),
                )
            )
        lines.append("")

    scopes = sorted({scope for spec in specs for scope in spec.scopes})
    lines.append("## OAuth scopes referenced")
    lines.append("")
    lines.extend(f"- `{scope}`" for scope in scopes)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    settings = Settings.load(ROOT / "config" / "config.example.yaml")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(settings), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
