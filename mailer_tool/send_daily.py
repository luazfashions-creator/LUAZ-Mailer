"""Unattended daily sender (for Task Scheduler / cron).

  python send_daily.py --business "LUAZ Labs" --template newsletter
  python send_daily.py --business "LUAZ Labs" --template newsletter --file inbox/today.csv --dry-run

SMTP password comes from the environment variable MAILER_PASSWORD.
Template = templates/<name>.json (create it in the GUI via "Save template").
"""
import argparse
import json
import os
import sys

import mailer as m

p = argparse.ArgumentParser()
p.add_argument("--template", required=True)
p.add_argument("--business", required=True, help='business name, e.g. "LUAZ" or "LUAZ Labs"')
p.add_argument("--file", help="CSV/Excel file; default = newest file in inbox/")
p.add_argument("--attach", nargs="*", default=[], help="file names from the business's data folder to attach")
p.add_argument("--dry-run", action="store_true", help="show counts, send nothing")
p.add_argument("--allow-resend", action="store_true", help="do not skip those already mailed today")
a = p.parse_args()

known = m.list_businesses()
if a.business not in known:
    sys.exit(f"Unknown business '{a.business}'. Available: {', '.join(known)}")
m.set_business(a.business)
cfg = m.load_config()
tpl = json.loads((m.TEMPLATES / f"{a.template}.json").read_text(encoding="utf-8"))
src = a.file or m.latest_inbox_file()
if not src:
    sys.exit("No contact file found (inbox/ is empty and --file not given).")

df = m.read_table(src)
col = m.find_email_column(df)
if not col:
    sys.exit("Could not find an email column.")
ready, rep = m.clean_contacts(df, col, skip_sent_today=not a.allow_resend)
print(f"File: {src}\n{rep}")
if a.dry_run or ready.empty:
    sys.exit(0)

sent, failed = m.send_batch(cfg, os.environ.get("MAILER_PASSWORD", ""), ready,
                            tpl["subject"], tpl["body"], tpl["html"],
                            attachments=m.load_attachments(a.attach), progress=lambda i, t, e, s, f: print(f"{i}/{t} {e} sent={s} failed={f}"))
print(f"Done. sent={sent} failed={failed}")
sys.exit(1 if failed else 0)
