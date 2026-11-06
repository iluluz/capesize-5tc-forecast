# 01 · GitHub repository setup (tonight)

Goal: one repository the whole team works in from tonight, with data kept out of Git, a protected
`main` branch and a fixed folder layout so the ML part and the text (DL) part plug into each other.

---

## 1. Decisions (proposed; change before creating the repo if needed)

| Item | Proposal | Why |
|---|---|---|
| Visibility | **Public** (as created, `github.com/iluluz/capesize-5tc-forecast`) | Fine for code and docs, so **no licensed data or values ever go in** (Baltic Exchange, Wind, Clarksons). Switch to Private in Settings if the team prefers; on a free personal account branch protection then stops working. |
| Owner | Personal account `iluluz`, teammates added as collaborators | Simplest; move to an organization later if needed (Settings → Transfer). |
| Name | `capesize-5tc-forecast` | |
| Layout | **Monorepo**: data pipelines + ML + text branch + docs | One place for the shared contracts (dates, horizons, file formats). |
| Data | **Not in Git.** Shared drive (OneDrive / Google Drive) + a manifest with SHA-256 hashes in the repo | Licences; file size; reproducibility through the hashes. |
| Default branch | `main`, protected: PR + 1 approval, no force push | |
| Merge style | Squash merge; branch names `feat/…`, `fix/…`, `data/…`, `docs/…` | Clean history. |
| Python | 3.11 or 3.12, one `requirements.txt` (+ optional `requirements-dl.txt` for torch/transformers) | The DL stack is heavy; ML-only members need not install it. |

## 2. Folder layout

```
capesize-5tc-forecast/
├─ README.md                    # what the project is, how to set up, who owns what
├─ .gitignore                   # data/, *.xlsx, *.parquet, .venv/, mlruns/, .env
├─ requirements.txt             # pandas, numpy, openpyxl, pyarrow, scikit-learn, lightgbm, statsmodels, mapie, matplotlib
├─ requirements-dl.txt          # torch, transformers, sentence-transformers
├─ .env.example                 # DATA_DIR=D:/…/shared-drive/capesize-data   (each member sets their own .env)
├─ data/                        # gitignored; local copy of the shared drive
│  ├─ workbooks/                # the 5 delivered workbooks (1_, 2_, 3_, 4_, 6_)
│  ├─ text/                     # raw headlines (DL part)
│  └─ processed/                # parquet feature store, OOS predictions
├─ data_manifest.csv            # file, version/date, owner, SHA-256, source, licence note   (committed)
├─ data_pipeline/
│  └─ portwatch_customs/        # the existing capesize-5tc scripts (items 3 and 6)
├─ src/capesize/
│  ├─ io.py                     # load workbooks -> tidy frames; check SHA-256 against the manifest
│  ├─ calendar.py               # Baltic trading-day grid, decision times, news cutoffs (shared contract)
│  ├─ features/                 # spot, ffa, fundamentals, portwatch, customs, fleet, calendar
│  ├─ targets.py                # y_{t,h} = ln(S_{t+h}/S_t)
│  ├─ models/                   # baselines, linear, lightgbm, conformal
│  ├─ eval/                     # walk-forward splitter (purge/embargo), metrics, DM test
│  └─ text/                     # headline collection, embedding, daily aggregation, text model
├─ notebooks/                   # exploration only; outputs stripped by pre-commit
├─ experiments/results.csv      # one row per run (or local MLflow, mlruns/ gitignored)
├─ tests/                       # leakage tests, target tests, calendar tests (small synthetic fixtures)
└─ docs/
   ├─ 01_GitHub_Repo_Setup.md
   ├─ 02_ML_Plan_Review.md
   ├─ 03_DL_Text_Branch_Design.md
   └─ decisions.md              # dated log of agreed contracts (cutoff, horizons, splits)
```

## 3. Tonight's checklist (repo owner, ~45 minutes)

Status 2026-11-05: steps 1 and 4 done (repo created, scaffold pushed). Steps 2, 3, 5–7 need the owner's
GitHub account / the shared drive.

1. ~~Create the repository~~ — done: `iluluz/capesize-5tc-forecast` (public).
2. **Invite members**: Repo → Settings → Collaborators → Add people (they get Write). Everyone accepts the
   email invite and turns on 2FA.
3. **Protect `main`**: Settings → Branches → Add branch ruleset (or classic rule) for `main`: require a pull
   request, 1 approval, require status check `test` (CI), block force pushes and deletions.
4. ~~Clone and add the scaffold~~ — done. For reference, the original commands were:
   ```powershell
   git clone https://github.com/<org>/capesize-5tc-forecast.git
   cd capesize-5tc-forecast
   # create the folders above, paste .gitignore lines, copy the three docs into docs/
   # copy the existing pipeline (history is short, a plain copy is fine):
   robocopy "D:\桌面文件\AI-edge项目\capesize-5tc" data_pipeline\portwatch_customs /E /XD .venv data .git
   git add . ; git commit -m "Scaffold: layout, docs, PortWatch/customs pipeline" ; git push
   ```
   `.gitignore` must contain at least: `data/`, `*.xlsx`, `*.parquet`, `*.csv.gz`, `.venv/`, `.env`,
   `mlruns/`, `__pycache__/`, `.ipynb_checkpoints/`. Exception: `!data_manifest.csv`, `!experiments/results.csv`.
5. **Shared drive**: create `capesize-data/` with `workbooks/` and `text/`; upload the **final** workbooks
   (note: the PortWatch file in the shared project folder is an old version; use
   `capesize-5tc/outputs/3_Capesize_5TC_PortWatch_Weekly_Data.xlsx`). Record each file's SHA-256:
   `Get-FileHash <file> -Algorithm SHA256` → `data_manifest.csv`.
6. **Issues and board**: Projects → New (Board). Create one issue per work package in 02 and 03
   (labels: `data`, `ml`, `text-dl`, `eval`, `docs`; milestone per gate).
7. **Pre-commit (optional tonight, before the first notebook)**: `ruff` (lint/format) and `nbstripout`
   (removes notebook outputs, which could otherwise leak data into Git).

## 4. Working rules

- One issue → one branch → one PR. PR description says *what changed, how it was checked*.
- No data, no notebook outputs, no API keys in Git. Keys go in `.env` (gitignored).
- Changing a **shared contract** (calendar, cutoff, horizons, target formula, split dates, file schemas)
  needs a PR that edits `docs/decisions.md` and is approved by both the ML and the text-branch owners.
- Every model run appends a row to `experiments/results.csv`: date, git commit, model, horizon, test
  window, metrics. Failed runs too.
- `tests/` must pass before merge (CI with GitHub Actions running `pytest` and `ruff` can be added later).

## 5. Roles (fill in names)

| Area | Owner | Reviewer |
|---|---|---|
| Data pipelines + manifest | | |
| Feature store + calendar contract | | |
| Baselines + walk-forward/evaluation | | |
| LightGBM / linear models | | |
| Text collection + text branch (DL) | | |
| Docs, decisions log, final report | | |
