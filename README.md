# ChronoChina

ChronoChina（中国历史地理时间地图）是一个开源的历史地理研究原型。它把可追溯的 TGAZ/CHGIS 历史地点数据转换为可由 MapLibre 浏览的逐年地图，并明确区分空间邻近与历史谱系。

> 当前状态：Phase 1.4 前的产品与交互版本已冻结。仓库公开的是软件、测试和数据管道，不附带第三方历史数据或本地生成的数据集。

## 能做什么

- 在当前视口中按精确年份查询历史地点；
- 手动开关历史单位层级，不由缩放级别替用户决定；
- 在“点 + 标签”和“仅点”之间切换；
- 查看同坐标记录、来源、有效年代和基本详情；
- 切换现代参考底图；远程底图失败时历史图层仍可工作；
- 用可复现的 Python 管道下载、标准化、验证并生成 Web 数据。

## 数据语义底线

- `nearby != same entity`：空间接近不表示同一实体、前身、后继或改名。
- `entity identity != coordinate`：同一实体可以迁治；同一坐标也可对应多个实体。
- 同名不自动合并，异名不自动拆分。
- Historical Lineage 仅能由明确证据建立；本项目不会用最近邻自动生成谱系。
- 数据缺失不代表历史上没有地点或没有变化。
- 年代使用闭区间语义；公元纪年没有 0 年。
- 离散历史切片不会被描述为连续 time series。

## 技术栈与目录

- Python 3.11+：数据下载、标准化、查询、enrichment 与 QA；
- React、TypeScript、Vite、MapLibre GL JS：浏览器端地图；
- pytest、Vitest、Playwright：自动化验证。

```text
pipeline/   Python 包和测试
web/        Web App
scripts/    Windows PowerShell 入口
data/       本地第三方数据与生成结果（默认不进入 Git）
docs/       公开工程、数据源与政策文档
```

## 从干净检出开始

环境要求：Git、Windows PowerShell、Python 3.11+，以及 Node.js `^20.19.0` 或 `>=22.12.0`。

```powershell
git clone https://github.com/Shuo-Niu/chrono_china.git
Set-Location chrono_china
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

脚本会创建项目专属 `.venv/`，按 `pyproject.toml` 安装 Python 依赖，并通过 `web/package-lock.json` 执行 `npm.cmd ci`。项目不会向系统 Python 安装依赖。

## 获取并生成真实数据

先阅读 [数据源说明](docs/data_sources.md)和[数据再分发政策](docs/data_redistribution_policy.md)。这些命令会访问第三方服务；使用者需要自行确认适用条款。

```powershell
# Phase 0：真实数据获取与 Gate 验证
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase0.ps1

# 后续 Web 数据
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_3_1c.ps1
```

原始文件写入 `data/raw/`，标准化结果写入 `data/intermediate/`，Web 可消费结果写入 `data/processed/`，QA 写入 `data/qa/`。这些目录中的生成内容默认不提交。详见 [data/README.md](data/README.md)。

## 运行 Web App

生成 `data/processed/` 后：

```powershell
Set-Location web
npm.cmd run dev
```

终端会显示本地 URL，通常为 `http://localhost:5173/`。请注意，根目录没有 `package.json`；所有 npm 命令都应在 `web/` 中运行。

## 测试

不需要第三方历史数据的公开发布测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_public.ps1
```

已经生成完整本地数据后，可运行全部测试和 E2E：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -E2E
```

## 已知数据限制

- 当前 canonical 数据来自 TGAZ/CHGIS 2016 snapshot；CHGIS V6 尚未迁移。
- 村镇/聚落数据主要来自 1820、1911 两个历史切片，不能解释为跨年代连续覆盖。
- 早期高层行政单位覆盖不均。
- 1912–1949 数据尚未接入。
- 当前版本不包含历史行政 polygon、王朝疆域或自动 Historical Lineage。

## 参与项目

提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)、[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)和 [SECURITY.md](SECURITY.md)。数据相关修改必须保留来源、获取时间、许可信息及原始标识，且不得以 mock 历史记录填补覆盖缺口。

## 许可

仓库中的原创软件和项目文档采用 [Apache License 2.0](LICENSE)。第三方数据、地图瓦片、API 响应和生成的数据集不因本仓库许可而被重新授权；具体归属和限制见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)与[数据再分发政策](docs/data_redistribution_policy.md)。
