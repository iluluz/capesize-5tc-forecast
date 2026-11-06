# data_pipeline

`portwatch_customs/` is a copy of the standalone `capesize-5tc` project that built workbooks 3 (PortWatch weekly)
and 6 (China customs monthly). Its own history is in `portwatch_customs/RUN_LOG.md`.

Paths inside the scripts are relative to `portwatch_customs/`:
- raw and interim data → `portwatch_customs/data/` (gitignored), outputs → `portwatch_customs/outputs/` (gitignored);
- workbook 2 (used for cross-checks) → folder in env var `CAPESIZE_WORKBOOKS` (see `.env.example`).

Run order: `pw_01` → `pw_02` → `pw_02b` → `pw_03` → `pw_04` → `build_workbooks.py` → `verify_workbook.py`;
customs: `cu_01` (Comtrade) → `cu_02` (platform CSVs) → `cu_04` (distances) → `cu_03` → `verify_workbook6.py`.
Monthly customs update: new platform export around the 20th of each month, then `cu_02` and `cu_03`.
