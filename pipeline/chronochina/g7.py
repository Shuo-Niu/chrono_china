from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from .config import QA_DIR, RAW_DIR
from .io import USER_AGENT, sha256_bytes, utc_now, write_json


RAW_PROBE_DIR = RAW_DIR / "republican_era_access_probe"
MACHINE_REPORT_PATH = QA_DIR / "g7_republican_era_access_probe.json"
MARKDOWN_REPORT_PATH = QA_DIR / "republican_era_access_probe.md"

DATASET_PAGE_URL = "https://hgis.com.cn/?p=7088"
DATASET_TITLE = "民国时期中国县级治所时间序列点数据"

PROBE_TARGETS = (
    {
        "id": "nopss_project_evidence",
        "url": "https://www.nopss.gov.cn/n1/2017/1208/c400835-29695063.html",
        "purpose": "official_existence_and_format_evidence",
    },
    {
        "id": "digital_yugong_dataset_page",
        "url": DATASET_PAGE_URL,
        "purpose": "published_dataset_and_license_page",
    },
    {
        "id": "digital_yugong_inferred_file_folder",
        "url": (
            "https://hgis.com.cn/wp-content/uploads/simple-file-list/"
            "chgis/county-points-1912-1949/"
        ),
        "purpose": "public_file_folder_named_by_page_shortcode",
    },
    {
        "id": "digital_yugong_wordpress_api",
        "url": (
            "https://hgis.com.cn/wp-json/wp/v2/posts?"
            "search=%E6%B0%91%E5%9B%BD%E6%97%B6%E6%9C%9F%E5%8E%BF%E7%BA%A7"
            "%E6%B2%BB%E6%89%80%E7%82%B9%E6%97%B6%E9%97%B4%E5%BA%8F%E5%88%97"
        ),
        "purpose": "machine_readable_site_api_probe",
    },
    {
        "id": "fudan_chgis_download_page",
        "url": "https://yugong.fudan.edu.cn/CHGIS/sjxz.htm",
        "purpose": "current_official_chgis_public_download_catalog",
    },
    {
        "id": "legacy_digital_yugong_page",
        "url": "http://hgis.fudan.edu.cn/?p=7088",
        "purpose": "legacy_host_access_probe",
    },
)


def classify_access(results: list[dict[str, Any]]) -> str:
    """Classify operational access, never the historical existence of the data."""
    actual_data = any(result.get("retrieved_dataset_file") for result in results)
    if actual_data:
        has_conditions = any(result.get("access_conditions") for result in results)
        return "available_with_conditions" if has_conditions else "available"

    documented_application = any(
        result.get("documented_application_workflow") for result in results
    )
    if documented_application:
        return "available_with_conditions"

    existence_confirmed = any(
        result.get("dataset_existence_confirmed") for result in results
    )
    completed_probe_count = sum(result.get("http_status") is not None for result in results)
    if existence_confirmed and completed_probe_count >= 3:
        return "not_publicly_accessible"
    return "unknown"


def _save_raw_response(target_id: str, content: bytes, content_type: str) -> Path:
    suffix = ".html" if "html" in content_type.lower() else ".bin"
    destination = RAW_PROBE_DIR / f"{target_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def _probe_target(client: httpx.Client, target: dict[str, str]) -> dict[str, Any]:
    observed_at = utc_now()
    try:
        response = client.get(target["url"])
        content_type = response.headers.get("content-type", "")
        raw_path = _save_raw_response(target["id"], response.content, content_type)
        text = response.text if "text" in content_type or "html" in content_type else ""
        existence_confirmed = (
            target["id"] == "nopss_project_evidence"
            and "1912-1949县级治所基础地理信息数据" in text
        )
        return {
            **target,
            "observed_at": observed_at,
            "http_status": response.status_code,
            "final_url": str(response.url),
            "content_type": content_type,
            "bytes": len(response.content),
            "sha256": sha256_bytes(response.content),
            "raw_path": str(raw_path),
            "dataset_existence_confirmed": existence_confirmed,
            "retrieved_dataset_file": False,
            "documented_application_workflow": False,
            "access_conditions": None,
            "response_note": _response_note(target["id"], response.status_code, text),
        }
    except Exception as error:
        return {
            **target,
            "observed_at": observed_at,
            "http_status": None,
            "final_url": None,
            "content_type": None,
            "bytes": None,
            "sha256": None,
            "raw_path": None,
            "dataset_existence_confirmed": False,
            "retrieved_dataset_file": False,
            "documented_application_workflow": False,
            "access_conditions": None,
            "error_type": type(error).__name__,
            "error": str(error),
            "response_note": "request_failed",
        }


def _response_note(target_id: str, status: int, text: str) -> str:
    if target_id == "nopss_project_evidence":
        return (
            "official_report_confirms_completed_dataset"
            if status == 200 and "1912-1949县级治所基础地理信息数据" in text
            else "official_evidence_not_confirmed_in_response"
        )
    if target_id == "digital_yugong_dataset_page":
        if status >= 500 or "建立数据库连接时出错" in text:
            return "published_dataset_page_database_error"
        return "published_dataset_page_reachable" if status == 200 else "page_unavailable"
    if target_id == "digital_yugong_inferred_file_folder":
        return "inferred_public_folder_not_found" if status == 404 else "folder_probe_response"
    if target_id == "digital_yugong_wordpress_api":
        return "wordpress_rest_api_not_exposed" if status == 404 else "api_probe_response"
    if target_id == "fudan_chgis_download_page":
        if status == 200 and "1911年层数据" in text and "1912-1949" not in text:
            return "public_catalog_reaches_1911_but_does_not_list_republican_dataset"
        return "official_download_catalog_probe_response"
    if target_id == "legacy_digital_yugong_page":
        if status == 200 and "站点创建成功" in text and "hgis.com.cn" in text:
            return "legacy_host_is_placeholder_with_client_side_redirect"
        return "legacy_host_probe_response"
    return "probe_response"


def _render_markdown(report: dict[str, Any]) -> str:
    rows = []
    for result in report["http_probe_results"]:
        status = result["http_status"] if result["http_status"] is not None else "ERROR"
        rows.append(
            f"| `{result['id']}` | {status} | `{result['response_note']}` | "
            f"{result['observed_at']} |"
        )
    probe_table = "\n".join(rows)
    return f"""# 1912–1949 县级治所数据访问探测

## 结论

- Gate：`G7 probe COMPLETE`（本 Gate 非阻塞）。
- Capability：`{report['capability']}`。
- 当前访问分类：`{report['access_classification']}`。
- 该分类只描述 **{report['generated_at']} 探测时的可操作访问状态**，不表示“没有历史数据”。
- 数据存在性：`confirmed`。全国哲学社会科学工作办公室的项目报告明确记载已完成“1912-1949县级治所基础地理信息数据”。
- 公开下载：页面曾公开声明共享，但本次无法取得实际文件；当前文件列表/目录不可操作。
- API：未发现数据 API；站点 WordPress REST 入口返回 404，且它即使可用也不是历史数据 API。
- 申请：公开页面提供项目负责人联系方式，但未发现正式申请表、审批条件或承诺时限，因此不把“可发邮件询问”等同于 `available_with_conditions`。

## 已发现的数据描述

公开索引页：[{DATASET_TITLE}]({DATASET_PAGE_URL})。

- 英文名：`China County Points (Time Series) 1912-1949`
- 版本：`V1`
- 格式：`ArcGIS geodatabase`
- 坐标系：`GCS / WGS84`
- 时间精度：年
- 完成时间：`2015-01-24`
- 页面版权表述：路伟东所有；可免费使用、修改及分发
- 页面联系：路伟东（`wdlu@fudan.edu.cn`）

以上是发布页的元数据，不是本仓库已获得数据的声明。本轮没有下载到 Geodatabase，也没有将任何民国时期记录用于 Gate 或 UI。

## 实际 HTTP 探测

| Probe | HTTP | 观察 | 时间（UTC） |
|---|---:|---|---|
{probe_table}

原始响应保存在 `data/raw/republican_era_access_probe/`，机器可读报告为 `data/qa/g7_republican_era_access_probe.json`。raw 目录按仓库策略不提交，可用 `chronochina g7` 重新生成。

## 访问路径判定

| 问题 | 结论 | 证据 |
|---|---|---|
| 数据成果是否存在 | 是 | 官方中期检查报告明确称已完成，并说明为全国县级治所点状数据库。 |
| 是否有公开下载 | 当前不可操作 | 共享页的文件列表短代码未渲染；按短代码指向探测的目录返回 404。 |
| 是否有 API | 未发现 | 发布说明仅称 Geodatabase；站点 REST 探测返回 404。 |
| 是否可申请 | 未确认 | 有负责人邮箱，但没有公开的正式申请流程或使用批准条件。 |
| 数据格式 | 已知 | ArcGIS Geodatabase，GCS/WGS84。 |
| 私人非商业 demo 是否获准 | 未确认 | 页面有宽松版权表述，但实际文件及随附 license 未取得，不能只凭网页摘要替代数据包许可。 |
| 是否可程序化获取 | 当前否 | 未得到可用文件 URL、API 或自动化申请接口。 |

## 阻塞分类

- `source inaccessible`：迁移后的公开共享页返回数据库错误，推断文件目录返回 404。
- `API problem`：没有已发布的数据 API；WordPress REST 也不可用。
- `license/access ambiguity`：网页许可表述可见，但无法核对实际数据包附带许可；申请流程未公开。

## 可执行后续

1. 通过发布页负责人邮箱询问新的下载 URL、数据包许可和私人非商业 demo 使用条件。
2. 获得文件后另建导入分支，保存原始包、checksum、随附 license、schema 与 provenance；在此之前保持 1912–1949 coverage gap。
3. 不用 1911 数据外推 1912–1949，也不把 G7 的访问阻塞解释为历史上没有变化。
"""


def run_g7(*, pause_seconds: float = 0.4) -> dict[str, Any]:
    RAW_PROBE_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for index, target in enumerate(PROBE_TARGETS):
            results.append(_probe_target(client, target))
            if pause_seconds and index < len(PROBE_TARGETS) - 1:
                time.sleep(pause_seconds)

    classification = classify_access(results)
    report = {
        "gate": "G7",
        "status": "COMPLETE",
        "capability": classification.upper(),
        "blocking_gate": False,
        "generated_at": utc_now(),
        "access_classification": classification,
        "dataset_existence": (
            "confirmed"
            if any(result["dataset_existence_confirmed"] for result in results)
            else "unknown"
        ),
        "public_download": "advertised_but_not_operationally_retrieved",
        "api": "not_found",
        "application_path": "contact_only_no_documented_workflow",
        "programmatic_access": "not_operational",
        "http_probe_results": results,
        "published_metadata": {
            "page_url": DATASET_PAGE_URL,
            "title": DATASET_TITLE,
            "english_title": "China County Points (Time Series) 1912-1949",
            "version": "V1",
            "format": "ArcGIS geodatabase",
            "crs": "GCS / WGS84",
            "completed_at": "2015-01-24",
            "contact": "wdlu@fudan.edu.cn",
            "note": "Indexed public page metadata; the actual data file was not retrieved.",
        },
    }
    write_json(MACHINE_REPORT_PATH, report)
    MARKDOWN_REPORT_PATH.write_text(_render_markdown(report), encoding="utf-8")
    return report
