"""Install this package into a throwaway dbt project on DuckDB, run the macros on 400 date pairs per calendar and
compare: currencies with QuantLib's calendars (independent holiday source and arithmetic), exchanges with
numpy.busday_count over the seed's holiday list (checks the SQL logic).

    pip install dbt-duckdb QuantLib numpy
    python -m unittest discover -s tests -v
"""
import csv
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, timedelta

import duckdb
import numpy as np
import QuantLib as ql

PKG = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
QL = {"USD": ql.UnitedStates(ql.UnitedStates.FederalReserve), "EUR": ql.TARGET(),
      "GBP": ql.UnitedKingdom(ql.UnitedKingdom.Settlement), "JPY": ql.Japan(), "NZD": ql.NewZealand()}


def seed(name):
    with open(os.path.join(PKG, "seeds", name), newline="") as f:
        return list(csv.DictReader(f))


class Dbt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cals = sorted({r["pf_calendar"] for r in seed("plainfold_business_days.csv")})
        rnd = random.Random(7)
        cls.pairs = []
        for c in cals:
            for _ in range(400):
                a = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 1096))
                b = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 1096))
                cls.pairs.append((c, a, b))
        os.makedirs(os.path.join(cls.tmp, "seeds"))
        os.makedirs(os.path.join(cls.tmp, "models"))
        with open(os.path.join(cls.tmp, "seeds", "pairs.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["calendar", "calendar_date", "d2"])
            w.writerows((c, a.isoformat(), b.isoformat()) for c, a, b in cls.pairs)
        with open(os.path.join(cls.tmp, "dbt_project.yml"), "w") as f:
            f.write('name: t\nversion: "1.0.0"\nconfig-version: 2\nprofile: t\nseeds:\n  t:\n    pairs:\n'
                    '      +column_types: {calendar: varchar, d1: date, d2: date}\n')
        with open(os.path.join(cls.tmp, "packages.yml"), "w") as f:
            f.write(f"packages:\n  - local: {PKG}\n")
        with open(os.path.join(cls.tmp, "profiles.yml"), "w") as f:
            f.write(f"t:\n  target: d\n  outputs:\n    d:\n      type: duckdb\n      path: {cls.tmp}/t.duckdb\n")
        cases = "\n  union all\n  ".join(
            # the caller's columns are deliberately named calendar / calendar_date (shadowing check)
            f"select calendar, calendar_date, d2, {{{{ plainfold_calendars.business_days_between('calendar_date', 'd2', '{c}') }}}} as n, "
            f"{{{{ plainfold_calendars.is_business_day('calendar_date', '{c}') }}}} as ok from {{{{ ref('pairs') }}}} "
            f"where calendar = '{c}'" for c in cals)
        with open(os.path.join(cls.tmp, "models", "out.sql"), "w") as f:
            f.write("{{ config(materialized='table') }}\n" + cases + "\n")
        env = dict(os.environ, DBT_PROFILES_DIR=cls.tmp)
        for cmd in (["dbt", "deps"], ["dbt", "build"]):
            r = subprocess.run(cmd, cwd=cls.tmp, env=env, capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(r.stdout[-3000:] + r.stderr[-2000:])
        con = duckdb.connect(os.path.join(cls.tmp, "t.duckdb"), read_only=True)
        cls.got = {(c, a, b): (n, ok) for c, a, b, n, ok in con.execute("select * from out").fetchall()}
        cls.edge = con.execute(
            "select {}, {}, {}, {}".format(*[
                s.replace("{{ ref('plainfold_business_days') }}", "plainfold_business_days")
                for s in ("(select bd.pf_is_business_day = 1 from {{ ref('plainfold_business_days') }} bd where bd.pf_calendar = 'USD' and bd.pf_date = date '2025-12-31')",
                          "(select bd.pf_is_business_day = 1 from {{ ref('plainfold_business_days') }} bd where bd.pf_calendar = 'USD' and bd.pf_date = date '2029-01-01')",
                          "0", "0")])).fetchone()
        cls.counts = con.execute("select (select count(*) from plainfold_holidays), (select count(*) from plainfold_business_days)").fetchone()
        con.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_edges_and_counts(self):
        self.assertEqual(self.edge[:2], (None, None))  # outside 2026-2028 -> null
        self.assertEqual(self.counts, (404, 15344))
        same = [k for k in self.got if k[1] == k[2]]
        for k in same:
            self.assertEqual(self.got[k][0], 0)

    def test_against_sources(self):
        hol = {}
        for r in seed("plainfold_holidays.csv"):
            hol.setdefault(r["pf_calendar"], []).append(r["pf_holiday_date"])
        checked = 0
        for c, a, b in self.pairs:
            n, ok = self.got[(c, a, b)]
            lo, hi = min(a, b), max(a, b)
            want = int(np.busday_count(lo.isoformat(), hi.isoformat(), holidays=hol.get(c, []))) * (1 if a <= b else -1)
            self.assertEqual(n, want, (c, a, b))
            self.assertEqual(bool(ok), bool(np.is_busday(a.isoformat(), holidays=hol.get(c, []))), (c, a))
            if c in QL:
                cal = QL[c]
                qa, qb = ql.Date(a.day, a.month, a.year), ql.Date(b.day, b.month, b.year)
                self.assertEqual(bool(ok), cal.isBusinessDay(qa), (c, a))
                lo, hi = (qa, qb) if a <= b else (qb, qa)
                # QuantLib counts business days in [lo, hi) with includeFirst=True, includeLast=False
                self.assertEqual(n, cal.businessDaysBetween(lo, hi, True, False) * (1 if a <= b else -1), (c, a, b))
            checked += 1
        self.assertEqual(checked, len(self.pairs))
        self.assertEqual(len(self.pairs), 14 * 400)


if __name__ == "__main__":
    unittest.main()
