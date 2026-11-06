# Run log
Date/time (UTC): 2026-11-04, raw pulls stamped 03:46Z–05:26Z (final files `*_20261104T052641Z`)
Agent / environment: Claude Code on Windows 11 (PowerShell), Python 3.12 venv (`.venv`), no browser;
Excel 16 used only to recalculate a copy of the output for check 10. Git is not installed.

## PortWatch
- **Working port service name:** `Daily_Ports_Data`. `Daily_Trade_Data` returns "Item does not exist or is
  inaccessible". Chokepoints: `Daily_Chokepoints_Data`, published as a *table* (id 0); its metadata URL often
  returns "Invalid URL" while `/query` works.
- **Unit of trade volumes:** metric tons. Source: the ArcGIS item description of `Daily_Ports_Data`
  (item 83b1bbc7b3354c5fb1f40673bb8f852e): "import_dry_bulk: total import volume (in metric tons) of all dry
  bulk carriers entering the port at this date"; the same wording for export_dry_bulk. Converted to 10k t (÷ 10,000).
  Saved as `data/raw/portwatch/item_Daily_Ports_Data_*.json`.
- **Licence/terms:** item licence field points to https://www.imf.org/external/terms.htm. Recommended citation:
  "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)." Raw data kept out of Git.
- **Chokepoint IDs:** chokepoint1 Suez Canal, chokepoint7 Cape of Good Hope, chokepoint4 Bab el-Mandeb Strait,
  chokepoint5 Malacca Strait (28 chokepoints in total).
- **Ports selected per role (with portid)** — full reasons in the `Port Selection` sheet:
  - BR_IRON: Itaqui port506, Tubarao port1328, Porto de Itaguai port2045, Guaiba Island Terminal port422,
    Porto do Acu port166, Ponta Ubu port2368 (2025: 382 Mt)
  - AU_IRON: Port Hedland port955, Port Walcott port981, Dampier port276 (2025: 844 Mt)
  - AU_COAL: Newcastle port816, Hay Point port458, Gladstone port398, Abbot Point port0 (2025: 326 Mt)
  - AU_BAUX: Weipa port1387; BR_BAUX: Trombetas port2373 (added by human decision, 2026-11-04)
  - ZA_ORE: Saldanha Bay port1133, Richards Bay port1099 (2025: 120 Mt)
  - CN_IMPORT: Qingdao port1069, Rizhao port1105, Shougang Jingtang port1195, Tangshan (Jingtang) port1266,
    Tianjin Xin Gang port1297, Lianyungang port644, Dalian port273, Zhoushan port1429, Ningbo port824,
    Zhanjiang port1426, Yantai port1410, Huanghua port154, Lanqiao Port port632 (last two added 2026-11-04)
  - Dropped (human decision 2026-11-04): GN_BAUX Kamsar port536, Conakry port258 (PortWatch ~15 Mt/yr vs
    ~180 Mt exported; offshore transshipment not captured). Not used: Qinhuangdao port1072, Vitoria port1368.
- **Rows pulled / date range / last date:** ports 97,240 rows (34 ports × 2,860 days), 2019-01-01 to
  2026-10-30; chokepoints 11,420 rows (4 × 2,855 days), 2019-01-01 to 2026-10-25. Last port date is 5 days
  before the pull. Weekly grid: 409 Fridays, 2019-01-11 to 2026-11-06; complete weeks 2019-01-18 to 2026-10-30.
- **Gaps found:** none. Every port has one row per calendar day (0 missing, 0 duplicates); every chokepoint
  likewise. No negative values. Zeros kept as genuine (calls 16,222, imports 57,366, exports 25,653 port-days).
  Incomplete weeks: the first week (data start on Tuesday 2019-01-01) and the current week (ports end Thursday
  2026-10-30; chokepoints end 2026-10-25), left blank. Last 3 complete weeks (2026-10-16, -23, -30) flagged
  "may be revised".
- **Weekly rule spot-check (3 random weeks, recomputed from daily rows):** CN_IMPORT w/e Fri 2025-07-04,
  AU_COAL w/e Fri 2019-07-12, GN_BAUX w/e Fri 2026-03-27 — all match exactly.
- **Cross-check vs Wind AU+BR (file 2 col F):** correlation levels = 0.796, 4-wk avg = 0.931, ratio of means
  (PortWatch/Wind) = 1.02, n = 405 weeks; **verdict: use the BR/AU iron ore volume series** (rule: 4-wk corr > 0.8).
- **Cross-check vs implied port arrivals (file 2 col K):** with 13 China ports (after adding Huanghua and
  Lanqiao) correlation levels = 0.645, 4-wk avg = 0.767, ratio of means = 0.94, n = 374 weeks (11 ports: 0.608 /
  0.738 / 0.77); **verdict: still below 0.8 → keep China port-call counts only**, not China import volumes.
  Note the teammate series is itself derived (inventory change + outflow), so part of the gap is on that side.
- **Workbook check (no. 10):** Excel full recalculation of a copy (output untouched) → 0 error cells on all 8
  sheets; all 8 derived formula columns equal an independent pandas computation (max |diff| < 1e-12); Long Table
  lags resolve for all 4,884 rows. `scripts/verify_workbook.py` → PASS.
- **Sanity:** Cape of Good Hope dry bulk transits rose from ~185–210/week (2019–23) to ~290–312 (2024–26) while
  Suez fell from ~139 (2023) to ~70 — the Red Sea rerouting is visible, as expected.

## Customs
- **UN Comtrade, keyless public preview** (`/public/v1/preview/C/M/HS`, tested 2026-11-04): one period per call,
  ≤500 records, HTTP 429 when calls are ~2 s apart (script waits 15 s). China (156) monthly imports by partner
  exist from between 2015-04 and 2016-03 (2014-01..2015-03 return 0 records) up to **2024-12**; 2025-01..2025-03
  returned 0 records (not yet reported). Several HS codes per call work (`cmdCode=2601,2606,2701,2702`).
  Keyless quota: ~50 calls, then HTTP 403 "Out of call volume quota. Quota will be replenished in hh:mm:ss";
  the script now sleeps until replenishment and resumes (already-saved months are skipped). Example check: 2024-12 iron ore
  from Australia netWgt 68,129,708,300 kg. `cu_01_fetch.py` pulls 2014-01..2024-12, HS 2601/2606/2701/2702, all
  partners, raw JSON per month in `data/raw/customs/`.
- **Primary source, customs platform (stats.customs.gov.cn), exported by hand by the human:** 11 quarterly GBK
  CSVs `customs_8digit_2024Q1..2026Q3.csv` (no UTC stamp in the name; saved 2026-11-04 ~11:02–11:15 local time).
  Query: import, USD, monthly, HS8 26011110,26011120,26011190,26011200,26012000,26060000,27011100,27011210,
  27011290,27011900,27012000,27021000,27022000, all partners. The first attempt (without 26011120, iron ore fines)
  was rejected: HS8 values did not add up to the HS4 values (e.g. AU 2024-01 2.59 bn vs 8.54 bn USD). With
  26011120, AU/BR 2024-01..03 HS8 sums equal the HS4 export exactly. Single queries over ~9 months were cut at
  2024-09 (row limit), hence quarterly files.
- `scripts/cu_02_check_platform.py`: 2024-01..2026-09, 33 months, every quarter complete, 4,269 rows, 0 duplicates,
  all units kg, no nulls, every key HS8 code present every month. Iron ore ~94–119 Mt/month, AU 52–71 Mt, BR 17–29 Mt.
- **Comtrade history:** 2016-01..2024-12 (108 months); 2014-01..2015-12 return 0 records, so the series start in
  2016-01 (handoff asked for 2014). Keyless quota (~50 calls) and one DNS drop handled by retries.
- **Workbook 6 built** by `scripts/cu_03_build_workbook.py`: `outputs/6_Capesize_5TC_China_Customs_Monthly.xlsx`,
  129 months (2016-01..2026-09), splice Comtrade < 2024-01 ≤ platform. Origins: iron ore AU/BR/ZA/CA; coal
  (2701+2702) AU/ID/RU/MN/CA; bauxite GN/AU/ID; plus other and total. Partner codes confirmed by name
  (platform 601 澳大利亚, 410 巴西, 244 南非, 501 加拿大, 112 印度尼西亚, 344 俄罗斯, 124 蒙古, 221 几内亚).
- **Comtrade vs platform (2024 overlap, all 12 months; 6 random months reported):** quantity max |diff| 0.006%
  (iron ore from AU), value max |diff| 0.06% → same statistics; splice is seamless.
- **Check 7 (totals):** listed origins + other = total, max |diff| 2e-12 (10k t). Comtrade sum of partners = its
  World row per HS4: value 0.000%, weight 0.000% (World weight reported in 358 of 432 month × HS4).
- **Check 8 (Jan/Feb):** both sources report January and February separately in every year 2016–2026, so no split
  was needed; `jan_feb_split` column present, all 0.
- **Check 9 (lagged correlation, customs AU+BR iron ore imports vs Wind AU+BR shipments aggregated to calendar
  months by spreading each week over its 7 days):** lag 0 r = 0.397, **lag 1 r = 0.437**, lag 2 r = 0.275
  (levels, n = 128); MoM % change r = 0.159 / 0.177 / −0.133. Peak at 1 month is consistent with voyage times, but
  the link is loose (port congestion, discharge timing, customs declaration timing).
- **PortWatch direction test (4.8.2):** same sign of MoM change — AU_IRON vs customs Australia 60% (lag 0), 54%
  (lag 1), 40% (lag 2); BR_IRON vs customs Brazil 47% / 54% / 61% (lag 0/1/2), 90–92 months. Weak at monthly
  frequency; Brazil best at 2 months (≈40-day voyage).
- **Check 10:** Excel recalculation of a copy → 0 error cells on all 7 sheets; all 38 derived formula columns equal
  pandas; Long Table 2,322 rows with lags resolved; tonne-mile columns blank while distances are empty →
  `verify_workbook6.py` PASS.
- **Release lag (verified 2026-11-05):** GACC announcement 2025 No. 240, *2026年中国海关统计数据公布时间表*
  (attachment downloaded from mofcom.gov.cn, saved as `data/raw/customs/gacc_2026_release_timetable_*.doc`):
  快讯 ~7th–14th, 月刊 18th, **在线查询数据 (stats.customs.gov.cn, the source used) the 20th** of the following
  month; note 7: no February release, January+February online data open on 20 March. → lag **20 days**, plus
  **28 extra days for January** (Long Table formula `=E+H+IF(MONTH(E)=1,Parameters!C…,0)`). The handoff's 18 days
  refers to 月刊, not the online query data. Earlier years' calendars not checked.
- **Sailing distances (2026-11-05):** `scripts/cu_04_distances.py`, searoute 1.6.0 (Apache-2.0, Eurostat MARNET
  network) between PortWatch port coordinates and Qingdao, Panama/Suez/Arctic excluded (Capesize routing):
  Port Hedland 3,531 nm; Tubarão 11,137; Saldanha Bay 8,007; Sept-Îles 14,811; Kamsar 11,448; Weipa 3,430;
  Pontianak (proxy for West Kalimantan bauxite ports) 2,329. Alternatives: Itaqui 12,042, Port Cartier 14,811.
  Model distances, not from a commercial distance table; BR/AU ratio 3.15 matches the usual ~11,000 vs ~3,500 nm.
  Inputs in `config/customs_parameters.csv` (committed). Tonne-mile columns now computed.
- **2014:** not available on the customs platform (starts 2015) nor on Comtrade (starts 2016) → unobtainable from
  free sources.
- **2015 (2026-11-05):** 4 quarterly platform files added; all complete, all key HS8 codes present. Annual totals:
  iron ore 952.5 Mt, coal 204.1 Mt, bauxite 55.3 Mt.
- **Comtrade 2016–2017 rejected (annual-total check):** coal 2016 167 Mt and bauxite 2016 8.9 Mt, far below China's
  published totals (≈256 Mt and ≈52 Mt, from memory, not re-sourced); bauxite ~0.6–1 Mt/month vs ≥6 Mt from 2018;
  Indonesian coal collapses in 2017-10..12. 2018–2023 annual totals match the published figures (iron ore
  1,064 / 1,069 / 1,170 / 1,120 / 1,106 / 1,179 Mt). **New source rule:** platform wherever it has the month;
  Comtrade only for months without platform data from 2018-01; 2016-01..2017-12 left blank (gap).
  Sources in the rebuilt workbook: platform 2015-01..2015-12 and 2024-01..2026-09; Comtrade 2018-01..2023-12;
  gap 2016-01..2017-12. 141 months, 2,106 Long Table rows. To close the gap, export 2016Q1..2017Q4 from the platform.
- **2016–2017 (2026-11-05, final):** the human exported 2016Q1..2017Q4 from the platform (8 files, complete, all key
  codes present). Annual totals: 2016 iron ore 1,024.0 Mt, coal 255.4 Mt, bauxite 51.7 Mt; 2017 1,074.7 / 270.7 /
  68.5 Mt — this confirms the Comtrade 2016–2017 shortfall. No level break at the 2017-12 → 2018-01 source change.
- **FINAL workbook 6:** 141 months, 2015-01..2026-09, **no gaps**. Sources: platform 2015-01..2017-12 and
  2024-01..2026-09; Comtrade 2018-01..2023-12 (identical to the platform in the 2024 overlap). 2,538 Long Table rows.
- **Check 9 (final):** lag 0 r = 0.474, **lag 1 r = 0.541**, lag 2 r = 0.419 (levels, n = 140); MoM % change
  0.182 / 0.173 / −0.100.
- **Check 10 (final, both workbooks):** Excel recalculation of copies → 0 error cells. Workbook 6: 40 derived
  columns (incl. tonne-mile) equal pandas, Long Table lags incl. January extra resolve → PASS. Workbook 3:
  `verify_workbook.py` → PASS.

## Deviations from this document
1. Port service is `Daily_Ports_Data`, not `Daily_Trade_Data`.
2. `ISO3 IN (...)` filters on `Daily_Ports_Data` fail or time out (5.9 M-row scans), so step A2 builds the
   candidate list from the small `PortWatch_ports_database` table (2,065 ports) and pulls data one `portid` at a
   time; candidates = handoff name hints + top 12 dry bulk ports per country.
3. The PortWatch server rejected 50–80% of requests at random (2026-11-03, a Tuesday update day, and
   overnight): "Invalid URL", "Unable to perform query", "Object reference not set", 504. Added up to 20
   retries per page and a per-port cache so runs resume. Identical requests succeed on retry, so these are
   server-side errors, not malformed queries.
4. `pw_common.query` stops on a short page instead of relying on the count endpoint (which often fails).
5. Extra step `pw_02b_write_selection.py` holds the port selection decision (editable), separate from ranking.
6. Added a `ZA ore ports exports` column (role ZA_ORE was in 3.4 but not in the 5.1 column list) and two flag
   columns in Weekly Data: `May be revised (last 3 weeks)` and `All port roles complete`.
7. A role-week is blank unless every port in the role reports all 7 days (only the first and current weeks).
8. Three identical `ports_daily_*.csv` raw files exist because the pull was resumed twice; the latest is used.
9. Check 10 used Excel (via COM) instead of LibreOffice, which is not installed.

## Items I could not do (and why)
1. **China customs platform by script:** `stats.customs.gov.cn` returns HTTP 412 (anti-bot challenge) to scripted
   requests; not bypassed. Resolved: the human exported the HS8 data by hand in a browser (see Customs).
2. **Check 11 (`git status`):** done by the human after installing Git: commit 7d9ba64, 16 tracked files, none under
   `data/` or `.venv/` (verified).
3. **2014 customs:** not available from any free source (platform starts 2015, Comtrade 2016).

## Decisions (human, 2026-11-04)
1. Huanghua and Lanqiao added to CN_IMPORT. 2. Weipa (AU_BAUX) and Trombetas (BR_BAUX) added.
3. Guinea dropped. 4. Customs: Wind export (steps in `MANUAL_STEPS.md`); Comtrade history pulled keyless.
Workbook rebuilt and re-verified after 1–3: `verify_workbook.py` → PASS (5,291 Long Table rows).

## Open questions
5. Weekly snapshots (3.8): should a scheduled weekly re-download be set up?
