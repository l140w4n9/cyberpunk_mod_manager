# -*- coding: utf-8 -*-
"""多样例依赖解析回归测试（需 Nexus API Key）。"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import (
    NEXUS_MOD_LINK_RE,
    collect_dependencies,
    fetch_nexus_mod_requirements,
    parse_dependencies_from_text,
)


@dataclass
class SampleCase:
    mod_id: int
    label: str
    expect_ids: set[int] | None = None
    forbid_ids: set[int] = field(default_factory=set)
    notes: str = ""


CASES = [
    SampleCase(
        18777,
        "Rebeccas Apartment DLC",
        expect_ids={107, 21422, 4198},
        forbid_ids={7871},
        notes="Nexus requirements 表格；描述里仅有 7871 前作链接",
    ),
    SampleCase(
        27967,
        "0-Engine",
        expect_ids={107, 7780, 1511},
        notes="KNOWN_MOD_DEPENDENCIES 硬编码补充",
    ),
    SampleCase(
        23032,
        "2nd Amendment Sign",
        forbid_ids=set(),
        notes="可选依赖 24453 应标 optional（若描述含链接）",
    ),
    SampleCase(
        9617,
        "V's Apartment AMM",
        notes="描述含 Requires + 安装步骤链接，应解析出真实前置",
    ),
    SampleCase(
        21422,
        "Native Interactions Framework",
        notes="框架模组，通常无 Nexus requirements",
    ),
    SampleCase(
        107,
        "Cyber Engine Tweaks",
        notes="基础框架，对照组",
    ),
]


async def analyze_case(case: SampleCase) -> dict:
    async with NexusClient() as client:
        details = await client.get_mod_details(case.mod_id)

    text = f"{details.summary}\n{details.description}"
    nexus_reqs = await fetch_nexus_mod_requirements(case.mod_id)
    text_only = parse_dependencies_from_text(
        text,
        exclude_mod_id=case.mod_id,
        owner_mod_id=case.mod_id,
    )
    text_strict = parse_dependencies_from_text(
        text,
        exclude_mod_id=case.mod_id,
        owner_mod_id=case.mod_id,
        strict=True,
    )
    collected = await collect_dependencies(
        case.mod_id, details.description, details.summary
    )

    raw_links = sorted({int(m.group(1)) for m in NEXUS_MOD_LINK_RE.finditer(text)})

    result = {
        "mod_id": case.mod_id,
        "label": case.label,
        "notes": case.notes,
        "nexus_requirements": [
            {"id": d["mod_id"], "name": d.get("name"), "source": d.get("source")}
            for d in sorted(nexus_reqs, key=lambda x: x["mod_id"])
        ],
        "text_parsed_loose": [d["mod_id"] for d in text_only],
        "text_parsed_strict": [d["mod_id"] for d in text_strict],
        "raw_links_in_description": raw_links,
        "collect_dependencies": [
            {
                "id": d["mod_id"],
                "name": d.get("name"),
                "source": d.get("source"),
            }
            for d in sorted(collected, key=lambda x: x["mod_id"])
        ],
        "checks": {},
    }

    collected_ids = {int(d["mod_id"]) for d in collected}

    if case.expect_ids is not None:
        missing = case.expect_ids - collected_ids
        extra_expected_miss = collected_ids - case.expect_ids
        result["checks"]["expect_all_present"] = not missing
        result["checks"]["missing_expected"] = sorted(missing)
        result["checks"]["unexpected_extra"] = sorted(
            extra_expected_miss - case.forbid_ids
        )

    forbidden_hit = sorted(case.forbid_ids & collected_ids)
    result["checks"]["forbidden_absent"] = not forbidden_hit
    result["checks"]["forbidden_found"] = forbidden_hit

    # 有 GraphQL 登记时，最终集合应优先与其一致
    if nexus_reqs:
        nexus_ids = {int(d["mod_id"]) for d in nexus_reqs}
        result["checks"]["nexus_subset_of_final"] = nexus_ids <= collected_ids
        false_positives = collected_ids - nexus_ids - {
            int(d["mod_id"]) for d in collected if d.get("source") in ("known", "optional")
        }
        result["checks"]["no_extra_parsed_when_nexus_present"] = not false_positives
        result["checks"]["extra_parsed_ids"] = sorted(false_positives)

    return result


async def main() -> None:
    results = []
    passed = 0
    failed = 0

    for case in CASES:
        row = await analyze_case(case)
        checks = row["checks"]
        case_ok = all(
            v
            for k, v in checks.items()
            if isinstance(v, bool)
        )
        row["passed"] = case_ok
        results.append(row)
        if case_ok:
            passed += 1
        else:
            failed += 1

        print(f"\n{'='*60}")
        print(f"#{row['mod_id']} {row['label']} — {'PASS' if case_ok else 'FAIL'}")
        print(f"说明: {row['notes']}")
        print(f"GraphQL nexusRequirements: {row['nexus_requirements']}")
        print(f"描述原始链接: {row['raw_links_in_description']}")
        print(f"文本解析(宽松): {row['text_parsed_loose']}")
        print(f"文本解析(严格): {row['text_parsed_strict']}")
        print(f"collect_dependencies: {row['collect_dependencies']}")
        print(f"检查项: {json.dumps(checks, ensure_ascii=False)}")

    print(f"\n{'='*60}")
    print(f"合计: {passed} 通过, {failed} 失败, 共 {len(CASES)} 个样例")

    out = Path(__file__).with_name("_dependency_samples_report.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入: {out}")


if __name__ == "__main__":
    from pathlib import Path

    asyncio.run(main())
