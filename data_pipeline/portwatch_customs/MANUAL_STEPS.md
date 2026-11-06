# 手动步骤：海关数据 + Git 检查

> 状态（2026-11-04）：
> - UN Comtrade **约 2015/16 ~ 2024-12** 的中国月度分国别进口（2014 年及 2015 年初 Comtrade 上没有中国月度数据），由 `scripts/cu_01_fetch.py` 用免 key 的 preview 接口拉取到 `data/raw/customs/`。
> - **2025-01 以后 Comtrade 上没有中国月度分国别数据**（实测返回 0 条）。最近月份必须用下面方案 A 或 B 补齐。

---

## 方案 A（推荐）：Wind EDB 导出

1. 打开 Wind 终端 → **经济数据库 EDB**。
2. 按关键词搜索指标。下表的指标名是 Wind 的常见写法，**未逐条核对**，以终端里搜索到的为准。
   - 进口数量选「**当月值**」，不要选累计值。
   - 频率：月。
   - 时间：2014-01 至最新。

   | 商品（HS） | 搜索关键词 | 需要的来源国 |
   |---|---|---|
   | 铁矿砂及其精矿（2601） | `进口数量:铁矿砂及其精矿` | 合计、澳大利亚、巴西、南非、印度、加拿大、秘鲁、几内亚（Simandou 2025 年底起出货） |
   | 煤及褐煤（2701+2702） | `进口数量:煤及褐煤` | 合计、印度尼西亚、澳大利亚、俄罗斯、蒙古、加拿大、美国、哥伦比亚、菲律宾 |
   | 铝矿砂及其精矿（2606） | `进口数量:铝矿砂及其精矿` | 合计、几内亚、澳大利亚、印度尼西亚、巴西 |

3. 把所有指标勾进同一张表，点**导出 Excel**。导出时保留表头里的「指标 ID」「单位」「频率」「来源」行，这些是溯源用的。
4. 文件名带 UTC 时间戳，放进 `data/raw/customs/`，例如 `wind_customs_20261105T020000Z.xlsx`。**导出后不要手动改这个文件。**
5. 注意：
   - **1 月和 2 月**：海关常只公布 1–2 月合并数，Wind 里 1 月可能为空或是合并值。原样保留，处理脚本会单独标记。
   - **单位**：可能是「万吨」或「吨」。看表头的单位行，不要猜。
   - Choice、iFinD 的步骤基本相同（宏观数据库 → 海关 → 进口商品分国别）。选哪个都行，但**全部数据用同一个来源**。

## 方案 B（免费，较慢）：海关总署在线查询平台，人手在浏览器操作

脚本访问 `stats.customs.gov.cn` 会被拦截（HTTP 412），按规则不能绕过，但人用浏览器手动查询没问题。

1. 在浏览器打开 http://stats.customs.gov.cn/ 。如果出现验证码，自己完成。
2. 查询条件：
   - 进出口：**进口**
   - 时间：**月度**；选起止年月。一次查询的范围可能有限，按年分批查。
   - 商品编码：`2601`、`2606`、`2701`、`2702`（4 位品目）
   - 贸易伙伴：全部，或者只选上表中的国家
   - 输出指标：**第一数量**（千克或吨）和美元金额
3. 查询后下载 CSV/Excel，原样放进 `data/raw/customs/`，例如 `customs_2601_2025_20261105T020000Z.csv`。
4. 这个页面的界面我没有实际看过，以上步骤是**按常见布局写的，未核实**。如果实际字段名不同，以页面为准。

## 方案 C（补充）：UN Comtrade 免费 key

只有想更快更新、或需要补 2025 年数据时才需要。现在拉历史数据不需要 key。

1. 注册 https://comtradeplus.un.org 。
2. 登录后进入 API portal（comtradedeveloper.un.org），订阅免费的 **comtrade - v1**，复制 Primary key。
3. 在 PowerShell 里运行：
   ```powershell
   $env:COMTRADE_KEY = "你的key"
   cd D:\桌面文件\AI-edge项目\capesize-5tc\scripts
   ..\.venv\Scripts\python.exe cu_01_fetch.py 2025 2026
   ```
4. 中国官方数据报送到 Comtrade 通常晚一年以上，所以 2025 年可能仍然是空的。最近月份还是要靠方案 A 或 B。

**为什么三份数据都要：**
- 方案 A 或 B 是主数据源。
- Comtrade 用来交叉核对（对应 handoff 的 check 9）。
- PortWatch 的中国港口到港量和海关数据做滞后相关性检验（check 8）。

---

## Git 检查（check 11）

1. 安装 Git for Windows，二选一：
   ```powershell
   winget install --id Git.Git -e
   ```
   或者从 https://git-scm.com/download/win 下载安装。装完后**重开终端**。
2. 首次使用先设置身份：
   ```powershell
   git config --global user.name  "你的名字"
   git config --global user.email "iluluz@mit.edu"
   ```
3. 在项目目录运行：
   ```powershell
   cd D:\桌面文件\AI-edge项目\capesize-5tc
   git init
   git status
   ```
4. **检查点**：`git status` 的未跟踪列表里应该**没有** `data/raw/`、`data/interim/`、`.venv/`，因为它们已被 `.gitignore` 排除。应该能看到 `scripts/`、`outputs/`、`README.md`、`RUN_LOG.md`、`requirements.txt`、`.gitignore`。
5. 确认无误后再提交：
   ```powershell
   git add .
   git commit -m "PortWatch weekly data pipeline and workbook 3"
   ```
   如果 `outputs/` 里的 xlsx 不想进仓库，先在 `.gitignore` 里加一行 `outputs/*.xlsx`。

---

## 第 6 个工作簿的三项收尾

> 航运距离和发布滞后都填在 `config/customs_parameters.csv`，**不要只在 Excel 里改**：每次重建都会覆盖工作簿。
> 填完后运行：`cd scripts` → `..\.venv\Scripts\python.exe cu_03_build_workbook.py`

### 1. 补 2014–2015 年海关数据（可选）
1. 在海关平台按之前的设置查询：进口、美元、分月展示，8 位编码（同一串），贸易伙伴留空。
2. 按季度查 2014Q1 到 2015Q4，共 8 个文件。命名 `customs_8digit_2014Q1.csv` 等，放进 `data/raw/customs/`。
   - 先看年份下拉框能不能选到 2014。选不到就记下最早能选的年份，然后停下。
   - 2014–2015 年的税则可能和现在不同。如果某个编码查不到，用「选择编码」展开 2601、2606、2701、2702，把当年的全部子目勾上。
3. 运行 `cu_02_check_platform.py`。它会检查每个季度是否完整、关键编码每个月是否都有。如果提示缺编码，就按第 2 步重查。
4. 运行 `cu_03_build_workbook.py`，工作簿会自动从 2014-01 开始。
5. 量级核对：2014 年中国从澳大利亚进口铁矿，每月应该在几千万吨的量级。数量明显偏小，通常是漏了粉矿编码。

> **状态（2026-11-05）**：第 2、3 项已由 Claude 完成，见 RUN_LOG。下面的步骤保留作参考，以后要换数据来源时可以照着做。
> 第 1 项：海关平台最早只能查到 2015 年，2014 年没有免费来源可取。

### 2. 航运距离（吨海里指标用）
1. 每条航线选一个**代表性装货港**，卸货港统一用 Qingdao：
   - 铁矿：澳大利亚 Port Hedland；巴西 Tubarão 或 Ponta da Madeira；南非 Saldanha Bay；加拿大 Sept-Îles 或 Port-Cartier
   - 铝土矿：几内亚 Kamsar；澳大利亚 Weipa；印尼选一个西加里曼丹的出口港
2. 去一个可以引用的来源查海里数：
   - 免费：sea-distances.org，输入两个港口，读取 nautical miles。
   - 付费：Netpas Distance、Clarksons、BIMCO 等。
   - 同一份表**全部用同一个来源**。巴西、几内亚、加拿大东岸的航线按绕好望角计算，并在 source 里写明路线。
3. 填进 `config/customs_parameters.csv` 对应的行：
   - `load_port`：装货港
   - `distance_nm`：海里数，只填数字
   - `source`：网站名称和网址，加上航线说明
   - `access_date`：查询日期，例如 2026-11-05
4. 合理性核对：巴西到青岛的距离应该是澳大利亚到青岛的约 3 倍。差得太远，就是港口选错或单位错了。
5. 一种商品的所有距离都填齐后，重建工作簿，对应的吨海里列才会出数。

### 3. 核对发布滞后（现为 18 天）
1. 打开海关总署网站 www.customs.gov.cn → 「海关统计」栏目，找到「**2026年海关统计数据发布时间表**」。具体栏目名以网站为准。
2. 在表里找到**分国别、分商品的详细统计数据**（不是月初的快报总值）每个月的发布日期。
3. 对最近 6 个月逐月计算：发布日期减去数据月份的月末，得到天数。取**最大值**，这样回测时不会提前用到还没发布的数据。
4. 也可以用平台直接验证：在某个月的 18–20 日前后查询上个月的数据，看是否已经能查到。
5. 把天数填进 CSV 最后一行（`LAG,ALL`）的 `distance_nm` 列（这一行借用这列放天数）。在 `source` 列写明时间表的网址和查询日期，然后重建工作簿。

---

## 数据放好之后

把 Wind（或海关平台）的导出文件放进 `data/raw/customs/` 后告诉我，我会接着做：

1. 写处理脚本 `cu_02`，统一单位、处理 1–2 月合并数。
2. 生成 `outputs/6_Capesize_5TC_China_Customs_Monthly.xlsx`。
3. 跑 check 7–9：
   - 7：合计数与各国之和的一致性
   - 8：与 PortWatch 中国港口到港量的滞后相关
   - 9：与 Comtrade 对比
