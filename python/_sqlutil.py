"""Shared helpers: parse and run the queries in sql/*.sql.

Keeping one parser means the dashboard and the verifier both execute the exact
same SQL that lives in the .sql files (single source of truth).
"""
from __future__ import annotations
import glob
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SQL_DIR = os.path.join(ROOT, "sql")
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "marketplace.db")


def split_queries(text: str):
    """Yield (label, sql) for each ';'-terminated statement in a .sql file."""
    for chunk in text.split(";"):
        lines = chunk.splitlines()
        label = None
        for ln in lines:
            s = ln.strip()
            if s.startswith("-- Q"):
                label = s[2:].strip()
                break
        code = "\n".join(ln for ln in lines if not ln.strip().startswith("--")).strip()
        if not code:
            continue
        head = code.lstrip().upper()
        if head.startswith("WITH") or head.startswith("SELECT"):
            yield (label or "(unlabelled query)", code)


def run_all(con, sql_dir: str = SQL_DIR) -> dict[str, pd.DataFrame]:
    """Run every query in every .sql file; return {short_key: dataframe}.

    short_key is like '02_growth_marketing::Q1' so callers can fetch a specific
    result without copying SQL.
    """
    out = {}
    for path in sorted(glob.glob(os.path.join(sql_dir, "*.sql"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            text = f.read()
        for label, sql in split_queries(text):
            qid = label.split("|")[0].strip() if "|" in label else label
            out[f"{stem}::{qid}"] = pd.read_sql(sql, con)
    return out
