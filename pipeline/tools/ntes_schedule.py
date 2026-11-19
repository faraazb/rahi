#!/usr/bin/env python3
"""Print NTES schedules as JSON, for checking one train by hand.

Usage: uv run --project pipeline python pipeline/tools/ntes_schedule.py 61017 52103 > out.json
(The pipeline itself saves the raw pages with `mumbailocal ntes-fetch`.)
"""
import json
import sys
import time

from mumbailocal import ntes

if __name__ == "__main__":
    client = ntes.Client()
    res = []
    for n in sys.argv[1:]:
        res.append(ntes.parse_page(client.schedule_page(n)[1], n))
        time.sleep(ntes.DELAY_S)  # be polite to a public enquiry service
    json.dump(res, sys.stdout, indent=1)
