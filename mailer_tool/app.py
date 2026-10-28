"""Bulk Mailer GUI.  Run:  streamlit run app.py"""
import streamlit as st

import mailer as m
from richtext_widget import rich_editor

st.set_page_config(page_title="Bulk Mailer", page_icon="✉️", layout="wide")
st.title("✉️ Bulk Mailer")

import os
_gate = os.environ.get("MAILER_APP_PASSWORD")          # set this when the app runs on a server
if _gate and not st.session_state.get("_authed"):
    _p = st.text_input("Password to open the mailer", type="password")
    if _p and _p == _gate:
        st.session_state["_authed"] = True
        st.rerun()
    elif _p:
        st.error("Wrong password.")
    st.stop()

import json
from pathlib import Path

import pandas as pd

NEW = "➕ New business"
businesses = m.list_businesses()
def _create_business():
    try:
        name = m.create_business(st.session_state.get("new_business_name", ""))
        st.session_state["business"] = name        # select it right away
        st.session_state["new_business_name"] = ""
    except ValueError as ex:
        st.session_state["biz_error"] = str(ex)


choice = st.radio("Business", businesses + [NEW], horizontal=True, key="business",
                  help="Each business has its own sender, templates, inbox, sent log and unsubscribe list.")
if choice == NEW:
    n1, n2 = st.columns([3, 1])
    n1.text_input("Name of the new business", key="new_business_name")
    n2.button("Create", on_click=_create_business)
    if st.session_state.pop("biz_error", None):
        st.error("Please enter a business name.")
    st.stop()

m.set_business(choice)          # every file below now belongs to this business
profile = choice                # (used as a key prefix for the widgets)
cfg = m.load_config()
st.caption(f"Sending as **{cfg['from_name'] or choice}** <{cfg['from_email'] or 'not set yet - see tab 2'}> "
           f"via {cfg['smtp_host']}")
st.caption(f"Your settings, templates, logs and files are stored permanently in: `{m.DATA_ROOT}`")
tab_send, tab_settings, tab_log, tab_data = st.tabs(
    ["1 · Send", "2 · Sender settings", "3 · Sent log", "4 · Data folder"])

# ---------------- Settings ----------------
with tab_settings:
    K = lambda n: f"{profile}__{n}"
    fields = ["smtp_host", "smtp_port", "security", "username", "from_name", "from_email",
              "reply_to", "unsubscribe_mailto", "delay_seconds", "footer"]
    for f in fields:                      # seed widget state from the saved file once per account
        st.session_state.setdefault(K(f), cfg[f])

    def apply_preset():
        p = st.session_state[K("preset")]
        if p in m.PRESETS:
            for k, v in m.PRESETS[p].items():
                st.session_state[K(k)] = v

    st.session_state.setdefault(K("preset"), m.preset_for(cfg))
    st.session_state.setdefault(K("password"), m.load_secret())
    st.selectbox("Provider preset (fills host / port / security)", ["(choose)"] + list(m.PRESETS),
                 key=K("preset"), on_change=apply_preset)
    st.caption("SendGrid: username is the word apikey, password is your SendGrid API key (starts with SG.).  "
               "Gmail: App Password needed.  Zoho: use the host matching your data centre "
               "(.eu for Germany) and an App-Specific Password if 2FA is on.  "
               "Daily limits: Gmail ~500, Zoho free ~200.")
    c1, c2 = st.columns(2)
    cfg["smtp_host"] = c1.text_input("SMTP host", key=K("smtp_host"))
    cfg["smtp_port"] = int(c2.number_input("Port", step=1, key=K("smtp_port")))
    sec = ["STARTTLS", "SSL", "NONE"]
    cfg["security"] = c1.selectbox("Security", sec, key=K("security"))
    cfg["username"] = c2.text_input("SMTP username (empty = use From email)", key=K("username"))
    st.session_state[K("password")] = st.text_input(
        "SMTP password / API key - press Enter after pasting",
        type="password", value=st.session_state.get(K("password"), ""))
    remember = st.checkbox("Remember this key (saved as a plain file in this business's folder, so anyone "
                           "who can open this app can send). Untick and save to forget it.",
                           value=m.has_saved_secret(), key=K("remember"))
    cfg["from_name"] = c1.text_input("From name", key=K("from_name"))
    cfg["from_email"] = c2.text_input("From email", key=K("from_email"))
    cfg["reply_to"] = c1.text_input("Reply-To (optional)", key=K("reply_to"))
    cfg["unsubscribe_mailto"] = c2.text_input(
        "Unsubscribe mailbox (optional, adds List-Unsubscribe header)", key=K("unsubscribe_mailto"))
    cfg["delay_seconds"] = c1.number_input("Delay between emails (seconds)", min_value=0.0, step=0.5,
                                           key=K("delay_seconds"),
                                           help="Slower looks more natural to providers. For a new mailbox use 10-30 s.")
    cfg["footer"] = st.text_area("Footer added to every email (address / how to unsubscribe)",
                                 height=80, key=K("footer"))
    st.markdown("**Signature** - added under every email of this business")
    cfg["signature_html"] = rich_editor(cfg.get("signature_html", ""), key=K("sig"), min_height=110,
                                        placeholders=["Name"])
    lg1, lg2 = st.columns([3, 1])
    logo_up = lg1.file_uploader("Logo for the signature (PNG / JPG, optional)", type=["png", "jpg", "jpeg", "gif"],
                                key=K("logoup"))
    cfg["signature_logo_width"] = int(lg2.number_input("Logo width (px)", min_value=40, max_value=600,
                                                       value=int(cfg.get("signature_logo_width") or 120), step=10,
                                                       key=K("logow")))
    cur_logo = m.logo_file(cfg)
    remove_logo = False
    if cur_logo:
        lg1.image(str(cur_logo), width=min(cfg["signature_logo_width"], 300), caption="Current logo")
        remove_logo = lg1.checkbox("Remove current logo", key=K("logorm"))
    if st.button("Save settings"):
        if logo_up is not None:
            fname = "signature_logo" + (Path(logo_up.name).suffix.lower() or ".png")
            (m.CONFIG_FILE.parent / fname).write_bytes(logo_up.getvalue())
            cfg["signature_logo"] = fname
        elif remove_logo:
            cfg["signature_logo"] = ""
        m.save_config(cfg)
        pw_now = st.session_state.get(K("password"), "")
        if remember and pw_now:
            m.save_secret(pw_now)
        elif not remember:
            m.delete_secret()
        st.success(f"Saved sender settings for {profile}" + (" - key remembered." if remember and pw_now else
                                                              " (key not saved)."))

# ---------------- Log ----------------
with tab_log:
    import pandas as pd
    if m.SENT_LOG.exists():
        log = pd.read_csv(m.SENT_LOG, dtype=str).fillna("")
        st.dataframe(log.iloc[::-1], width="stretch")
        st.download_button("Download log", log.to_csv(index=False), "sent_log.csv")
    else:
        st.write("Nothing sent yet.")
    st.markdown("**Unsubscribe list:** add addresses (one per line) to this business's `unsubscribed.csv`; they are never mailed.")

# ---------------- Data folder ----------------
with tab_data:
    st.caption(f"Files kept for **{profile}** only (lists, attachments, anything). "
               f"Folder on your computer: `{m.DATA}`")
    n_up = st.session_state.get("dataup_n", 0)
    ups = st.file_uploader("Add files - CSV / Excel lists, PDFs, images, anything (several at once)",
                           accept_multiple_files=True, key=f"dataup_{profile}_{n_up}")
    if ups and st.button("💾 Save to Data folder"):
        for f in ups:
            m.save_to_data(f.name, f.getvalue())
        st.session_state["dataup_n"] = n_up + 1
        st.session_state["data_msg"] = f"Saved {len(ups)} file(s)."
        st.rerun()
    if st.session_state.get("data_msg"):
        st.success(st.session_state.pop("data_msg"))

    files = m.list_data()
    st.markdown(f"**{len(files)} file(s)**" if files else "_No files yet. Add some above._")
    for i, f in enumerate(files):
        c = st.columns([5, 1.6, 2.6, 1.2, 1.2])
        c[0].write(f"📄 {f['name']}")
        c[1].write(m.human_size(f["size"]))
        c[2].write(f["modified"])
        if f["size"] <= 50 * 1024 * 1024:
            c[3].download_button("⬇️", m.data_path(f["name"]).read_bytes(), file_name=f["name"],
                                 key=f"dl_{profile}_{i}_{f['name']}", help="Download")
        if c[4].button("🗑️", key=f"del_{profile}_{i}_{f['name']}", help="Delete"):
            st.session_state["pending_delete"] = (profile, f["name"])
            st.rerun()

    pend = st.session_state.get("pending_delete")
    if pend and pend[0] == profile:
        st.warning(f"Delete **{pend[1]}** permanently? This cannot be undone.")
        y, n = st.columns(2)
        if y.button("Yes, delete it", type="primary"):
            try:
                m.delete_data(pend[1])
            except FileNotFoundError:
                pass
            k = f"att_{profile}"                     # also drop it from the attachment picker
            st.session_state[k] = [x for x in st.session_state.get(k, []) if x != pend[1]]
            st.session_state.pop("pending_delete", None)
            st.rerun()
        if n.button("Cancel"):
            st.session_state.pop("pending_delete", None)
            st.rerun()

    if files:
        pv = st.selectbox("Preview a file", ["(none)"] + [f["name"] for f in files], key=f"pv_{profile}")
        if pv != "(none)":
            p = m.data_path(pv)
            low = pv.lower()
            if low.endswith((".csv", ".xlsx", ".xls", ".xlsm")):
                try:
                    st.dataframe(m.read_table(p).head(100), width="stretch")
                except Exception as ex:  # noqa: BLE001
                    st.error(f"Could not read this file: {ex}")
            elif low.endswith((".txt", ".md", ".json", ".html", ".log")):
                st.code(p.read_text(encoding="utf-8", errors="replace")[:3000])
            elif low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                st.image(p.read_bytes())
            else:
                st.info("No preview for this file type (you can still download or attach it).")

    st.divider()
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**Export**")
        st.download_button("📦 Export all as ZIP", m.export_zip() if files else b"",
                           file_name=f"{profile}_data.zip", disabled=not files)
    with e2:
        st.markdown("**Import**")
        z = st.file_uploader("Add the files of a ZIP", type=["zip"], key=f"zipimp_{profile}_{n_up}")
        if z and st.button("Import ZIP"):
            try:
                cnt = m.import_zip(z.getvalue())
                st.session_state["dataup_n"] = n_up + 1
                st.session_state["data_msg"] = f"Imported {cnt} file(s)."
                st.rerun()
            except Exception as ex:  # noqa: BLE001
                st.error(f"Import failed: {ex}")

# ---------------- Send ----------------
with tab_send:
    # Display order: 1 message, 2 recipients, 3 review & send.  Recipients are computed FIRST (below) only so
    # that the message editor knows the column names - changing recipients never touches the message.
    box_msg = st.container()
    box_rec = st.container()
    box_go = st.container()

    # ===== 2 - Recipients =====
    with box_rec:
        st.subheader("2 · Recipients")
        st.caption("Choose or change recipients at any time - your message above stays exactly as it is.")
        MODES = ["Upload file (CSV / Excel)", "Saved list (Data folder)", "Type or paste emails"]
        mode = st.radio("Where are the recipients?", MODES, horizontal=True, key=f"mode_{profile}")
        df = None
        if mode == MODES[0]:
            up = st.file_uploader("Today's CSV / Excel file", type=["csv", "xlsx", "xls", "xlsm"],
                                  key=f"upload_{profile}")
            source = up
            if up is None:
                latest = m.latest_inbox_file()
                if latest:
                    st.info(f"No upload - using newest file in this business's inbox folder: **{latest.name}**")
                    source = latest
            else:
                if st.button("💾 Keep a copy of this file in the Data folder"):
                    st.success(f"Saved as {m.save_to_data(up.name, up.getvalue())}")
            if source is not None:
                df = m.read_table(source)
        elif mode == MODES[1]:
            saved = m.list_contact_files()
            if saved:
                pick = st.selectbox("Saved list", saved, key=f"saved_{profile}")
                df = m.read_table(m.data_path(pick))
            else:
                st.info("No saved lists yet. Add CSV / Excel files in the **4 · Data folder** tab.")
        manual = None
        if mode == MODES[2] or st.checkbox("Also add typed emails", key=f"also_{profile}"):
            txt = st.text_area("Emails - one per line, or separated by commas / semicolons. "
                               "Optional name after the address: `anna@example.com, Anna` or `Anna <anna@example.com>`",
                               height=140, key=f"manual_{profile}",
                               placeholder="anna@example.com, Anna\nbob@example.com")
            manual = m.parse_manual_emails(txt)
            if not manual.empty:
                s1, s2 = st.columns([3, 1])
                list_name = s1.text_input("Save these typed emails as a list (name)", key=f"listname_{profile}")
                if s2.button("Save list") and list_name.strip():
                    st.success("Saved as " + m.save_to_data(list_name.strip() + ".csv",
                                                            manual.to_csv(index=False).encode("utf-8")))
        typed = manual is not None and not manual.empty
        email_col = "Email"
        if df is None and not typed:
            df = pd.DataFrame(columns=["Email", "Name"])
            st.info("No recipients chosen yet - you can already write your message above. "
                    "Pick recipients here whenever you are ready.")
        elif df is None:                                 # typed emails only
            df = manual
            st.caption(f"{len(manual)} typed address(es). Use {{Name}} in your message if you add names.")
        else:
            guess = m.find_email_column(df)
            cols0 = list(df.columns)
            email_col = st.selectbox("Which column holds the email address?", cols0,
                                     index=cols0.index(guess) if guess in cols0 else 0)
            if typed:                                    # list/file + typed emails
                manual = manual.rename(columns={"Email": email_col})
                df = pd.concat([df, manual], ignore_index=True).fillna("")
                st.caption(f"Added {len(manual)} typed address(es) to the list.")
        cols = list(df.columns)
        SKIP = {"today": "today", "in the last 7 days": 7, "in the last 30 days": 30,
                "ever (any time before)": "ever", "don't skip anyone": None}
        skip_label = st.selectbox("Skip addresses I already emailed successfully ...", list(SKIP), index=0,
                                  key=f"skip_{profile}",
                                  help="Use 'ever' for campaigns so nobody gets the same mail twice, "
                                       "and to continue a run that was interrupted.")
        if len(df):
            ready, rep = m.clean_contacts(df, email_col, skip_window=SKIP[skip_label])
        else:
            ready = pd.DataFrame(columns=list(df.columns) + ["_email"])
            rep = {"total": 0, "invalid": 0, "duplicates": 0, "unsubscribed": 0, "already_sent_today": 0, "ready": 0}

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Rows", rep["total"])
        k2.metric("Invalid", rep["invalid"])
        k3.metric("Duplicates", rep["duplicates"])
        k4.metric("Unsubscribed / already sent", rep["unsubscribed"] + rep["already_sent_today"])
        k5.metric("Will receive", rep["ready"])
        if len(ready):
            with st.expander("Preview recipients"):
                st.dataframe(ready.drop(columns=["_email"]).head(200), width="stretch")

    # ===== 1 - Message =====
    with box_msg:
        st.subheader("1 · Message")
        ph_cols = [c for c in cols if not c.startswith("_")]
        st.caption("Personalise with column names: " + ", ".join("{" + c + "}" for c in ph_cols))
        templates = sorted(p.stem for p in m.TEMPLATES.glob("*.json"))
        import json
        chosen = st.selectbox("Load saved template", ["(new)"] + templates)
        tpl = {"subject": "", "body": "", "html": False}
        if chosen != "(new)":
            tpl = json.loads((m.TEMPLATES / f"{chosen}.json").read_text(encoding="utf-8"))
        subject = st.text_input("Subject", tpl["subject"], key=f"s_{chosen}")
        FMT = ["Rich text (bold, colours, links, lists ...)", "Plain text"]
        fmt = st.radio("Message format", FMT, index=0 if (chosen == "(new)" or tpl["html"]) else 1,
                       horizontal=True, key=f"fmt_{profile}_{chosen}")
        is_html = fmt == FMT[0]
        if is_html:
            start = tpl["body"] if tpl["html"] else (
                __import__("html").escape(tpl["body"]).replace("\n", "<br>") if tpl["body"] else "")
            body = rich_editor(start, key=f"rb_{profile}_{chosen}", placeholders=ph_cols, min_height=240)
        else:
            body = st.text_area("Body", tpl["body"] if not tpl["html"] else m.html_to_text(tpl["body"]),
                                height=260, key=f"b_{profile}_{chosen}")
        n1, n2 = st.columns([3, 1])
        name = n1.text_input("Save as template (name)", "")
        if n2.button("Save template") and name.strip():
            (m.TEMPLATES / f"{name.strip()}.json").write_text(
                json.dumps({"subject": subject, "body": body, "html": is_html}), encoding="utf-8")
            st.success("Template saved.")

        st.markdown("**Attachments & signature**")
        att_up = st.file_uploader("Attach files from your computer (sent with every email)",
                                  accept_multiple_files=True, key=f"attup_{profile}")
        att_names = st.multiselect("... and/or attach files from the Data folder",
                                   [f["name"] for f in m.list_data()], key=f"att_{profile}")
        attachments = m.load_attachments(att_names) + [m.attachment_from_bytes(f.name, f.getvalue())
                                                       for f in att_up or []]
        if attachments:
            tot = sum(len(x[3]) for x in attachments)
            st.caption(f"{len(attachments)} attachment(s), {m.human_size(tot)} per email.")
            if tot > 10 * 1024 * 1024:
                st.warning("Large attachments: Gmail and Zoho limit total message size (about 20-25 MB) and "
                           "big attachments often land in spam. Consider a download link instead.")
        has_sig = bool(cfg.get("signature_html", "").strip() or m.logo_file(cfg))
        use_sig = st.checkbox("Add my signature" + ("" if has_sig else " (none set yet - see tab 2)"),
                              value=has_sig, key=f"usesig_{profile}_{has_sig}", disabled=not has_sig)
        cfg_send = cfg if use_sig else dict(cfg, signature_html="", signature_logo="")

    # ===== 3 - Review & send =====
    with box_go:
        st.subheader("3 · Review & send")
        n_ready = len(ready)
        if n_ready:
            shown = ", ".join(ready["_email"].head(5)) + (f" … (+{n_ready - 5} more)" if n_ready > 5 else "")
            st.write(f"**{subject.strip() or '(no subject yet)'}**  →  **{n_ready}** recipient(s): {shown}")
        else:
            st.write(f"**{subject.strip() or '(no subject yet)'}**  →  no recipients chosen yet (step 2)")
        sample = ready.iloc[0].to_dict() if n_ready else {c: f"[{c}]" for c in ph_cols}
        sample.setdefault("_email", "preview@example.com")
        with st.expander("Preview" + (" for first recipient" if n_ready else " (with placeholders)"), expanded=True):
            st.write("**Subject:**", m.render(subject, sample))
            if is_html:
                import base64
                doc = m.full_html(cfg_send, sample, body, "PREVIEWLOGO" if m.logo_file(cfg_send) else None)
                lf = m.logo_file(cfg_send)
                if lf:
                    mime = "image/" + lf.suffix.lstrip(".").replace("jpg", "jpeg")
                    doc = doc.replace("cid:PREVIEWLOGO",
                                      f"data:{mime};base64," + base64.b64encode(lf.read_bytes()).decode())
                st.html("<div style='background:#fff;color:#222;padding:14px;border:1px solid #ddd;"
                        "border-radius:8px'>" + doc + "</div>")
            else:
                st.text(m.build_message(cfg_send, sample, subject, body, False).get_content())
            if attachments:
                st.caption("Attachments: " + ", ".join(x[0] for x in attachments))

        pw = st.session_state.get(f"{profile}__password", "")
        t1, t2 = st.columns([3, 1])
        test_to = t1.text_input("Send a test to (works even before you choose recipients)", cfg["from_email"])
        if t2.button("Send test"):
            try:
                row = dict(sample)
                row["_email"] = test_to
                m.send_one(cfg_send, pw, row, subject, body, is_html, attachments)
                st.success(f"Test sent to {test_to}")
            except Exception as ex:  # noqa: BLE001
                st.error(f"Test failed: {ex}")

        portion = st.number_input("Send only the first N now (0 = everyone). The rest stay unsent for a later run.",
                                  min_value=0, value=0, step=10, key=f"portion_{profile}",
                                  help="New mailboxes are throttled quickly. Start small (e.g. 20-30 per day) and "
                                       "increase slowly.")
        to_send = ready.head(int(portion)) if portion else ready
        n_send = len(to_send)
        ok_to_send = bool(subject.strip() and body.strip() and cfg["from_email"] and n_send)
        if not n_ready:
            st.caption("Choose recipients in step 2 to enable sending.")
        elif not (subject.strip() and body.strip()):
            st.caption("Write a subject and a message in step 1 to enable sending.")
        confirm = st.checkbox(f"I confirm I want to email {n_send} people now", disabled=not ok_to_send)
        if st.button("🚀 Send to all" if not portion else f"🚀 Send first {n_send}", type="primary",
                     disabled=not (ok_to_send and confirm)):
            bar = st.progress(0.0)
            status = st.empty()

            def progress(i, total, addr, sent, failed):
                bar.progress(i / total)
                status.write(f"{i}/{total} · {addr} · ✅ {sent} sent · ❌ {failed} failed")

            try:
                sent, failed = m.send_batch(cfg_send, pw, to_send, subject, body, is_html, progress,
                                            attachments=attachments)
            except Exception as ex:  # noqa: BLE001
                st.error(f"Could not start sending: {ex}")
                st.stop()
            if m.LAST_RUN.get("stopped_early"):
                st.error(f"⛔ Stopped early to protect your mailbox: the provider is refusing mail "
                         f"(sending limit / spam protection). Sent {sent}, failed {failed}, and "
                         f"{m.LAST_RUN['not_attempted']} addresses were NOT attempted. Provider said: "
                         f"{m.LAST_RUN['reason']}")
                st.info("Do not retry right away. Wait several hours (or a day), then send again with "
                        "'Skip addresses I already emailed ... ever' selected - only the unsent ones go out. "
                        "Use smaller portions and a longer delay in Sender settings.")
            elif failed:
                last = pd.read_csv(m.SENT_LOG, dtype=str).fillna("")
                last = last[last["status"] == "failed"].tail(1)
                st.error(f"Sent {sent}, failed {failed}. Last error: {last['error'].iloc[0] if len(last) else ''}")
            else:
                st.success(f"Done. Sent {sent}, failed {failed}. See the Sent log tab.")
