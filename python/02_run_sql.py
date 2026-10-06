"""
Run every query in sql/*.sql against the SQLite warehouse and print the
results. I use this as a quick sanity check after editing a query.

    python python/02_run_sql.py        # all files
    python python/02_run_sql.py 03     # only files starting with 03
"""
from __future__ import annotations
import glob
import os
import sqlite3
import sys
import pandas as pd
from _sqlutil import split_queries, DB_PATH, SQL_DIR

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    con = sqlite3.connect(DB_PATH)
    files = sorted(glob.glob(os.path.join(SQL_DIR, "*.sql")))
    n_ok = 0
    for path in files:
        base = os.path.basename(path)
        if filt and not base.startswith(filt):
            continue
        print("\n" + "#" * 78)
        print(f"# FILE: {base}")
        print("#" * 78)
        with open(path) as f:
            text = f.read()
        for label, sql in split_queries(text):
            print(f"\n>>> {label}")
            print("-" * 74)
            df = pd.read_sql(sql, con)
            with pd.option_context("display.max_rows", 14):
                print(df.to_string(index=False))
            n_ok += 1
    con.close()
    print(f"\n{'='*40}\n{n_ok} queries executed successfully.\n{'='*40}")


if __name__ == "__main__":
    main()
