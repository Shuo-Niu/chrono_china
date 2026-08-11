# ChronoChina

[English](README.md) | [简体中文](README.zh-CN.md)

ChronoChina（中国历史地理时间地图）是一个开源的历史地理研究原型。它把保留来源信息的 TGAZ/CHGIS 历史地点记录转换为 MapLibre 可浏览的精确年份地图，并明确区分空间邻近与历史谱系。

> 当前状态：Phase 1.4 前的产品与交互版本已冻结。本仓库公开软件、测试和数据管道，**不附带**第三方历史数据集或本地生成的地图数据集。

## 能做什么

- 在当前视口中按精确年份查询历史地点；
- 由用户明确开关历史单位层级，不随 zoom 自动切换；
- 在“点 + 标签”和“仅点”之间切换；
- 查看同坐标记录、来源、有效年代和基本详情；
- 切换现代参考底图，且历史图层不依赖远程底图成功加载；
- 通过可复现的 Python 管道下载、标准化、验证并生成 Web 数据。

## 历史数据语义

- `nearby != same entity`：空间接近不表示同一实体、前身、后继或改名。
- `entity identity != coordinate`：同一实体可以迁治；同一坐标也可对应多个实体。
- 同名不自动合并，异名不自动拆分。
- Historical Lineage 只能由明确证据建立；最近邻逻辑不会自动生成谱系。
- 数据缺失不代表历史上不存在地点或变化。
- 有效年代使用闭区间；公元纪年没有 0 年。
- 离散历史切片不会被描述为连续 time series。

## 技术栈与目录

- Python 3.11+：数据获取、标准化、查询、enrichment 与 QA；
- React、TypeScript、Vite、MapLibre GL JS：浏览器地图；
- pytest、Vitest、Playwright：自动化验证。

```text
pipeline/   Python 包和测试
web/        Web App
scripts/    Windows PowerShell 入口
data/       本地第三方/生成数据（被 Git 忽略）
docs/       公开工程与数据治理文档
```

## 从干净检出开始

环境要求：Git、Windows PowerShell、Python 3.11+，以及 Node.js `^20.19.0` 或 `>=22.12.0`。

```powershell
git clone https://github.com/Shuo-Niu/chrono_china.git
Set-Location chrono_china
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

脚本会创建项目专属 `.venv/`，按 `pyproject.toml` 安装 Python 依赖，并通过 `web/package-lock.json` 执行 `npm.cmd ci`，不会把项目依赖安装进系统 Python。

## 获取并生成真实数据

请先阅读[数据源说明](docs/data_sources.md)和[数据再分发政策](docs/data_redistribution_policy.md)。以下命令会访问第三方服务，其当前条款独立适用。

```powershell
# Phase 0：真实数据获取与 Gate 验证
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase0.ps1

# Web 数据集
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_3_1c.ps1
```

原始文件写入 `data/raw/`，标准化数据写入 `data/intermediate/`，Web 数据写入 `data/processed/`，QA 证据写入 `data/qa/`。这些目录中的生成内容不进入 Git。详见 [data/README.md](data/README.md)。

## 运行 Web App

生成 `data/processed/` 后：

```powershell
Set-Location web
npm.cmd run dev
```

终端会显示本地 URL，通常是 `http://localhost:5173/`。根目录没有 `package.json`；npm 命令应在 `web/` 中运行。

## 测试

不依赖第三方历史数据的公开发布测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_public.ps1
```

生成完整且获授权的本地数据后，运行全部测试和 E2E：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -E2E
```

## 数据权利与商用

软件开源不会让上游数据自动成为开放数据。项目原创代码与文档采用 Apache-2.0，可按该许可证商用；主要数据源另有条件：

| 数据源 | 是否允许商用 | 再分发/公开托管 |
|---|---|---|
| CHGIS/TGAZ 历史内容 | **尚未获得商用授权。** CHGIS 公布条款仅允许非商业学术/教育用途；商用必须另签协议。 | 整体或通过互联网再发布需要书面许可。不得提交 raw、normalized、processed、cache 或逐记录 QA 数据。 |
| GeoNames | CC BY 4.0 允许商用。 | 可再分发，但须署名、链接许可证，并在适用时说明修改。 |
| OpenStreetMap/OpenMapTiles/OpenFreeMap | 支持商用。 | 仍须遵守 ODbL、署名、衍生数据库同许可及托管服务条款。 |
| CHGIS V6 及其他研究候选源 | 当前产品未获得商用许可。 | 条款存在冲突或因数据集而异，需要独立权利审查，通常还需取得许可。 |

因此，代码仓库可以开源，但包含 CHGIS/TGAZ 历史记录的公开或商业部署，**不会因为本仓库开源而自动获得法律许可**。商业上线前应取得书面授权，或更换为商用兼容的历史数据源。本段是工程权利评估，不构成法律意见。

详见[第三方声明](THIRD_PARTY_NOTICES.md)、[数据源说明](docs/data_sources.md)和[数据再分发政策](docs/data_redistribution_policy.md)。

## 已知数据限制

- 当前 canonical source 是 TGAZ/CHGIS 2016 snapshot；尚未迁移 CHGIS V6。
- 村镇/聚落数据主要来自 1820、1911 两个历史切片，不是连续覆盖。
- 早期高层行政单位覆盖不均。
- 1912–1949 数据尚未接入。
- 当前版本不包含历史行政 polygon、王朝疆域或自动 Historical Lineage。

## 参与项目

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)、[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)和 [SECURITY.md](SECURITY.md)。数据修改必须保留来源、获取时间、许可信息与原始标识，不得用 mock 历史记录填补覆盖缺口。

## 许可

项目原创软件与文档采用 [Apache License 2.0](LICENSE)。第三方数据、托管瓦片、API 响应和生成数据集不因本仓库而被重新授权。
