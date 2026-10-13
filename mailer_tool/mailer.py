"""Core logic: load contacts, validate, build and send emails via SMTP."""
from __future__ import annotations

import csv
import html as _html
import io
import os
import shutil
import json
import mimetypes
import re
import zipfile
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent


def _data_root() -> Path:
    """Where settings, templates, logs and files live. NOT inside the app folder, so installing a new
    version of the app never resets anything. Override with the MAILER_DATA_DIR environment variable."""
    env = os.environ.get("MAILER_DATA_DIR")
    root = Path(env).expanduser() if env else Path.home() / "LUAZ Mailer"
    try:
        (root / "businesses").mkdir(parents=True, exist_ok=True)
        return root
    except OSError:                                  # e.g. read-only home: fall back to the app folder
        return BASE


DATA_ROOT = _data_root()
BUSINESSES_DIR = DATA_ROOT / "businesses"  # one sub-folder per business, fully separate data
# The paths below are switched per business by set_business():
CONFIG_FILE = BASE / "config.json"
SENT_LOG = BASE / "sent_log.csv"           # who was emailed, when, ok/failed
UNSUBSCRIBED = BASE / "unsubscribed.csv"   # one email per line
INBOX = BASE / "inbox"                     # drop the daily file here
TEMPLATES = BASE / "templates"
DATA = BASE / "data"                       # per-business file storage (lists, attachments, anything)
CURRENT = {"name": ""}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

DEFAULT_CONFIG = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "security": "STARTTLS",      # STARTTLS | SSL | NONE
    "username": "",
    "from_name": "",
    "from_email": "",
    "reply_to": "",
    "delay_seconds": 1.0,        # pause between emails (be gentle with the provider)
    "unsubscribe_mailto": "",    # e.g. unsubscribe@yourdomain.com
    "footer": "",                # postal address / unsubscribe text, appended to every mail
    "signature_html": "",        # rich-text signature added under every message
    "signature_logo": "",        # file name of the logo stored in the business folder
    "signature_logo_width": 120, # logo width in pixels
}


# ---------- config ----------
PRESETS = {
    "Gmail": {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "security": "STARTTLS"},
    "Zoho Mail (EU / Germany)": {"smtp_host": "smtp.zoho.eu", "smtp_port": 587, "security": "STARTTLS"},
    "Zoho Mail (US / global)": {"smtp_host": "smtp.zoho.com", "smtp_port": 587, "security": "STARTTLS"},
    "Zoho Mail (India)": {"smtp_host": "smtp.zoho.in", "smtp_port": 587, "security": "STARTTLS"},
    "Brevo": {"smtp_host": "smtp-relay.brevo.com", "smtp_port": 587, "security": "STARTTLS"},
    "Amazon SES (eu-central-1)": {"smtp_host": "email-smtp.eu-central-1.amazonaws.com", "smtp_port": 587, "security": "STARTTLS"},
}


def clean_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _-]", "", name or "").strip()


def set_business(name: str) -> Path:
    """Point every path (config, templates, inbox, log, unsubscribe list) at this business."""
    global CONFIG_FILE, SENT_LOG, UNSUBSCRIBED, INBOX, TEMPLATES, DATA
    name = clean_name(name)
    root = BUSINESSES_DIR / name
    INBOX, TEMPLATES, DATA = root / "inbox", root / "templates", root / "data"
    for d in (root, INBOX, TEMPLATES, DATA):
        d.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE, SENT_LOG, UNSUBSCRIBED = root / "config.json", root / "sent_log.csv", root / "unsubscribed.csv"
    CURRENT["name"] = name
    return root


def _first_run_setup() -> None:
    """Create the two starting businesses; adopt files from older versions of this tool."""
    import shutil
    BUSINESSES_DIR.mkdir(exist_ok=True)
    luaz = BUSINESSES_DIR / "LUAZ"
    labs = BUSINESSES_DIR / "LUAZ Labs"
    for d in (luaz, labs):
        (d / "inbox").mkdir(parents=True, exist_ok=True)
        (d / "templates").mkdir(exist_ok=True)
        (d / "data").mkdir(exist_ok=True)
    # LUAZ = the existing (Gmail) setup
    cfg = dict(DEFAULT_CONFIG, **PRESETS["Gmail"], from_name="LUAZ")
    if (BASE / "config.json").exists():
        cfg.update(json.loads((BASE / "config.json").read_text(encoding="utf-8")))
    (luaz / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    for f in ("sent_log.csv", "unsubscribed.csv"):
        if (BASE / f).exists():
            shutil.copy(BASE / f, luaz / f)
    if (BASE / "templates").exists():
        for t in (BASE / "templates").glob("*.json"):
            shutil.copy(t, luaz / "templates" / t.name)
    # LUAZ Labs = the new Zoho sender
    cfg2 = dict(DEFAULT_CONFIG, **PRESETS["Zoho Mail (EU / Germany)"],
                from_name="LUAZ Labs", from_email="info@luazwellness.de")
    if (BASE / "config_zoho.json").exists():
        cfg2.update(json.loads((BASE / "config_zoho.json").read_text(encoding="utf-8")))
    (labs / "config.json").write_text(json.dumps(cfg2, indent=2), encoding="utf-8")


def list_businesses() -> list[str]:
    BUSINESSES_DIR.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in BUSINESSES_DIR.iterdir()):
        shipped = BASE / "businesses"                # starter / copied-over folders next to the app
        if shipped.resolve() != BUSINESSES_DIR.resolve() and shipped.is_dir() \
                and any(p.is_dir() for p in shipped.iterdir()):
            shutil.copytree(shipped, BUSINESSES_DIR, dirs_exist_ok=True)
        else:
            _first_run_setup()
    return sorted(p.name for p in BUSINESSES_DIR.iterdir() if p.is_dir())


def create_business(name: str) -> str:
    name = clean_name(name)
    if not name:
        raise ValueError("Please enter a business name.")
    set_business(name)
    if not CONFIG_FILE.exists():
        save_config(dict(DEFAULT_CONFIG, from_name=name))
    return name


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg: dict) -> None:
    # The password is never written to disk.
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ---------- data folder (per business) ----------
MAX_IMPORT_BYTES = 200 * 1024 * 1024


def safe_filename(name: str) -> str:
    name = Path(str(name).replace("\\", "/")).name.strip()          # drop any folder part
    name = re.sub(r"[^\w .()\-+@]", "_", name).strip(". ")
    return name or "file"


def _unique(name: str) -> Path:
    p = DATA / safe_filename(name)
    n = 1
    while p.exists():
        p = DATA / f"{Path(safe_filename(name)).stem} ({n}){Path(safe_filename(name)).suffix}"
        n += 1
    return p


def save_to_data(name: str, content: bytes) -> str:
    """Store a file in this business's data folder (never overwrites: adds ' (1)' if needed)."""
    DATA.mkdir(parents=True, exist_ok=True)
    p = _unique(name)
    p.write_bytes(content)
    return p.name


def list_data() -> list[dict]:
    DATA.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(DATA.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file() and not p.name.startswith("."):
            st_ = p.stat()
            out.append({"name": p.name, "size": st_.st_size,
                        "modified": datetime.fromtimestamp(st_.st_mtime).strftime("%Y-%m-%d %H:%M")})
    return out


def data_path(name: str) -> Path:
    p = (DATA / safe_filename(name)).resolve()
    if p.parent != DATA.resolve() or not p.is_file():
        raise FileNotFoundError(name)
    return p


def delete_data(name: str) -> None:
    data_path(name).unlink()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def export_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in list_data():
            z.write(data_path(f["name"]), arcname=f["name"])
    return buf.getvalue()


def import_zip(content: bytes) -> int:
    """Add every file in a zip to the data folder (folders are flattened; unsafe names cleaned)."""
    n = 0
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        infos = [i for i in z.infolist() if not i.is_dir()
                 and "__MACOSX" not in i.filename and not Path(i.filename).name.startswith(".")]
        if sum(i.file_size for i in infos) > MAX_IMPORT_BYTES:
            raise ValueError("Zip is larger than 200 MB uncompressed.")
        for i in infos:
            save_to_data(Path(i.filename).name, z.read(i))
            n += 1
    return n


def list_contact_files() -> list[str]:
    return [f["name"] for f in list_data() if f["name"].lower().endswith((".csv", ".xlsx", ".xls", ".xlsm"))]


def load_attachments(names: list[str]) -> list[tuple]:
    """[(filename, maintype, subtype, bytes)] for files in the data folder."""
    out = []
    for nme in names or []:
        p = data_path(nme)
        ctype, _ = mimetypes.guess_type(p.name)
        main, sub = (ctype or "application/octet-stream").split("/", 1)
        out.append((p.name, main, sub, p.read_bytes()))
    return out


# ---------- contacts ----------
def read_table(source) -> pd.DataFrame:
    """source: path or uploaded file object with .name"""
    name = str(getattr(source, "name", source)).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(source, dtype=str)
    else:
        if hasattr(source, "seek"):
            source.seek(0)
        df = pd.read_csv(source, dtype=str, sep=None, engine="python",
                         encoding_errors="replace")
    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def parse_manual_emails(text: str) -> pd.DataFrame:
    """Accepts emails separated by new lines, commas, semicolons or spaces.
    Also understands 'Name <a@b.com>' and 'a@b.com, Name' (second item on a line = Name)."""
    rows = []
    for line in re.split(r"[\n\r]+", text or ""):
        line = line.strip()
        if not line:
            continue
        found = re.findall(r"[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", line)
        if not found:
            rows.append({"Email": line, "Name": ""})      # keep it so it shows up as 'invalid'
            continue
        name = ""
        if len(found) == 1:
            rest = line.replace(found[0], "")
            name = re.sub(r"[<>;,\"]", " ", rest).strip()
        for addr in found:
            rows.append({"Email": addr, "Name": name})
    return pd.DataFrame(rows, columns=["Email", "Name"], dtype=str)


def find_email_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if "mail" in c.lower():
            return c
    for c in df.columns:  # fall back to a column that looks like emails
        sample = df[c].astype(str).head(20)
        if len(sample) and sample.str.match(EMAIL_RE).mean() > 0.6:
            return c
    return None


def latest_inbox_file() -> Path | None:
    files = [p for p in INBOX.iterdir()
             if p.suffix.lower() in (".csv", ".xlsx", ".xls", ".xlsm")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _read_emails(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        return {r[0].strip().lower() for r in rows if r and "@" in r[0]}


def sent_today() -> set[str]:
    if not SENT_LOG.exists():
        return set()
    today = datetime.now().strftime("%Y-%m-%d")
    log = pd.read_csv(SENT_LOG, dtype=str).fillna("")
    ok = log[(log["status"] == "sent") & log["timestamp"].str.startswith(today)]
    return set(ok["email"].str.lower())


def clean_contacts(df: pd.DataFrame, email_col: str, skip_sent_today=True):
    """Returns (ready_df, report_dict)."""
    df = df.copy()
    df["_email"] = df[email_col].astype(str).str.strip().str.lower()
    report = {"total": len(df)}

    valid = df["_email"].str.match(EMAIL_RE)
    report["invalid"] = int((~valid).sum())
    df = df[valid]

    before = len(df)
    df = df.drop_duplicates("_email")
    report["duplicates"] = before - len(df)

    unsub = _read_emails(UNSUBSCRIBED)
    mask = df["_email"].isin(unsub)
    report["unsubscribed"] = int(mask.sum())
    df = df[~mask]

    if skip_sent_today:
        done = sent_today()
        mask = df["_email"].isin(done)
        report["already_sent_today"] = int(mask.sum())
        df = df[~mask]
    else:
        report["already_sent_today"] = 0

    report["ready"] = len(df)
    return df.reset_index(drop=True), report


# ---------- message ----------
class _Safe(dict):
    def __missing__(self, key):
        return ""


def render(template: str, row: dict) -> str:
    """Replace {column_name} placeholders with row values; unknown ones become empty."""
    try:
        return template.format_map(_Safe({k: v for k, v in row.items()}))
    except (ValueError, IndexError):
        return template  # stray braces: send as-is


def html_to_text(h: str) -> str:
    """Readable plain-text version of the rich message (for the text/plain part)."""
    h = re.sub(r"(?is)<(script|style|head).*?>.*?</\1>", "", h or "")
    def link(mt):
        txt = re.sub(r"<[^>]+>", "", mt.group(2)).strip()
        url = mt.group(1).strip()
        return url if (not txt or txt == url) else f"{txt} ({url})"
    h = re.sub(r"(?is)<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", link, h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)<li[^>]*>", "\n- ", h)
    h = re.sub(r"(?i)</?(p|div|ul|ol|h[1-6]|tr|table|blockquote)(\s[^>]*)?>", "\n", h)
    h = _html.unescape(re.sub(r"<[^>]+>", "", h)).replace("\xa0", " ")
    h = re.sub(r"[ \t]+\n", "\n", h)
    return re.sub(r"\n{3,}", "\n\n", h).strip()


def _clean_html(h: str) -> str:
    """Remove scripts / event handlers from pasted content."""
    h = re.sub(r"(?is)<(script|iframe|object|embed).*?>.*?</\1>", "", h or "")
    h = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", h)
    return re.sub(r"(?i)javascript:", "", h)


def render_html(template: str, row: dict) -> str:
    """Like render(), but the substituted values are HTML-escaped (names like 'A & B' stay safe)."""
    safe = {k: _html.escape(str(v)) for k, v in row.items()}
    return render(_clean_html(template), safe)


def logo_file(cfg) -> Path | None:
    name = (cfg.get("signature_logo") or "").strip()
    p = CONFIG_FILE.parent / name if name else None
    return p if p and p.is_file() else None


def attachment_from_bytes(name: str, content: bytes) -> tuple:
    ctype, _ = mimetypes.guess_type(name)
    main, sub = (ctype or "application/octet-stream").split("/", 1)
    return (safe_filename(name), main, sub, content)


def full_html(cfg, row: dict, body: str, logo_cid: str | None = None) -> str:
    """The finished HTML mail: message + signature (+ logo) + footer."""
    parts = [f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#222">'
             f'{render_html(body, row)}</div>']
    sig = render_html(cfg.get("signature_html", ""), row).strip()
    if sig or logo_cid:
        img = ""
        if logo_cid:
            img = (f'<div style="margin-top:8px"><img src="cid:{logo_cid}" alt="" '
                   f'width="{int(cfg.get("signature_logo_width") or 120)}" style="border:0"></div>')
        parts.append(f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;margin-top:18px">'
                     f'{sig}{img}</div>')
    footer = cfg.get("footer", "").strip()
    if footer:
        parts.append("<hr style='margin-top:24px'><p style='font-size:12px;color:#777'>"
                     + _html.escape(footer).replace("\n", "<br>") + "</p>")
    return "".join(parts)


def build_message(cfg, row: dict, subject: str, body: str, is_html: bool, attachments=None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = render(subject, row)
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = row["_email"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg["from_email"].split("@")[-1])
    if cfg.get("reply_to"):
        msg["Reply-To"] = cfg["reply_to"]
    if cfg.get("unsubscribe_mailto"):
        msg["List-Unsubscribe"] = f"<mailto:{cfg['unsubscribe_mailto']}?subject=unsubscribe>"

    footer = cfg.get("footer", "").strip()
    sig_html = (cfg.get("signature_html") or "").strip()
    if is_html:
        logo = logo_file(cfg)
        cid = make_msgid(domain="luaz.local") if logo else None
        html_doc = full_html(cfg, row, body, cid.strip("<>") if cid else None)
        msg.set_content(html_to_text(html_doc))
        msg.add_alternative(html_doc, subtype="html")
        if logo:
            ctype, _ = mimetypes.guess_type(logo.name)
            main, sub = (ctype or "image/png").split("/", 1)
            msg.get_payload()[1].add_related(logo.read_bytes(), maintype=main, subtype=sub,
                                             cid=cid, filename=logo.name, disposition="inline")
    else:
        text = render(body, row)
        if sig_html:
            text += "\n\n" + html_to_text(render(sig_html, row))
        msg.set_content(text + (f"\n\n--\n{footer}" if footer else ""))
    for fname, main, sub, data in attachments or []:
        msg.add_attachment(data, maintype=main, subtype=sub, filename=fname)
    return msg


# ---------- sending ----------
def connect(cfg, password):
    host, port = cfg["smtp_host"], int(cfg["smtp_port"])
    ctx = ssl.create_default_context()
    if cfg["security"] == "SSL":
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        if cfg["security"] == "STARTTLS":
            server.starttls(context=ctx)
            server.ehlo()
    user = (cfg.get("username") or "").strip()
    if cfg["security"] != "NONE":           # encrypted providers always need a login
        user = user or (cfg.get("from_email") or "").strip()
    if user or cfg["security"] != "NONE":
        if not user:
            raise ValueError("SMTP username is empty. Enter your Gmail address in SMTP settings.")
        if not password:
            raise ValueError("SMTP password is empty. Paste the App Password in SMTP settings "
                             "(press Enter) - it is not remembered after a page refresh.")
        _login(server, cfg, user, password.replace(" ", ""))
    return server


def _login(server, cfg, user, password):
    """Log in with ONE method (PLAIN, else LOGIN) so the server's real answer is shown, and
    translate cryptic smtplib errors (e.g. 'please run connect() first') into plain advice."""
    adv = server.esmtp_features.get("auth", "").split()
    method = "PLAIN" if "PLAIN" in adv else ("LOGIN" if "LOGIN" in adv else None)
    if method:
        server.esmtp_features["auth"] = method
    region = (" Zoho EU accounts use smtp.zoho.eu, other regions smtp.zoho.com / smtp.zoho.in."
              if "zoho" in cfg["smtp_host"].lower() else "")
    hint = (f"Check: (1) the App Password is the NEWEST one, pasted without extra characters, "
            f"(2) username / From email is the full address '{user}', "
            f"(3) the host '{cfg['smtp_host']}' matches your account's region.{region} "
            f"(4) SMTP access is allowed for this mailbox.")
    try:
        server.login(user, password)
    except smtplib.SMTPAuthenticationError as e:
        raise ValueError(f"Login rejected by {cfg['smtp_host']} ({e.smtp_code}). {hint}") from e
    except (smtplib.SMTPServerDisconnected, ConnectionError) as e:
        raise ValueError(f"{cfg['smtp_host']} closed the connection during login - this is how servers "
                         f"usually answer a wrong password. {hint}") from e


def _log(rows):
    new = not SENT_LOG.exists()
    with SENT_LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "email", "status", "error"])
        w.writerows(rows)


def send_one(cfg, password, to_row: dict, subject, body, is_html, attachments=None):
    """Send a single email (used for test sends). Raises on failure."""
    server = connect(cfg, password)
    try:
        server.send_message(build_message(cfg, to_row, subject, body, is_html, attachments))
    finally:
        server.quit()


def send_batch(cfg, password, df, subject, body, is_html, progress=None, stop=None, attachments=None):
    """Send to every row of df. Logs each result. Returns (sent, failed)."""
    server = connect(cfg, password)
    sent = failed = 0
    total = len(df)
    try:
        for i, row in enumerate(df.to_dict("records"), 1):
            if stop and stop():
                break
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                try:
                    server.send_message(build_message(cfg, row, subject, body, is_html, attachments))
                except (smtplib.SMTPServerDisconnected, ConnectionError):
                    server = connect(cfg, password)  # reconnect once
                    server.send_message(build_message(cfg, row, subject, body, is_html, attachments))
                _log([[ts, row["_email"], "sent", ""]])
                sent += 1
            except Exception as e:  # noqa: BLE001
                _log([[ts, row["_email"], "failed", str(e)[:200]]])
                failed += 1
            if progress:
                progress(i, total, row["_email"], sent, failed)
            time.sleep(float(cfg.get("delay_seconds", 1)))
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return sent, failed
