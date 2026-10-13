# Bulk Mailer – daily CSV/Excel → email, no n8n, no SendGrid

## Where your data is stored (it survives updates)
Settings, signatures, templates, sent logs, unsubscribe lists and the data folders are stored OUTSIDE the app folder, in
`LUAZ Mailer/businesses/` inside your user folder (e.g. `/Users/nitin/LUAZ Mailer`). Installing a new version of the app
therefore never resets anything - just click **Save settings** once per business. Passwords are the only thing never saved.
To move data from an older version: before the first start, copy the old `businesses` folder into `LUAZ Mailer/businesses`
(or into the new app folder - it is used once when `LUAZ Mailer` is still empty). Back up by copying the `LUAZ Mailer` folder,
or use each business's *Export all as ZIP* for its data folder.
(Advanced: set the environment variable `MAILER_DATA_DIR` to store it elsewhere.)

## Quick start
Windows: double-click `start_windows.bat`.  Mac: double-click `start_mac_linux.command`.
The first run installs everything and opens the app at http://localhost:8501.
Test with `sample_contacts.csv` (put your own address in it) before using a real list.

## Manual setup (alternative)
1. Install Python 3.10+.
2. `pip install -r requirements.txt`
3. `streamlit run app.py` → opens the GUI in your browser.
4. Tab **2 · SMTP settings**: enter your mail server + login, press *Save settings*.
   - Gmail: host `smtp.gmail.com`, port 587, STARTTLS, username = your address,
     password = an **App Password** (Google Account → Security → 2-Step Verification → App passwords).
   - Any other provider (Outlook, your web host, Zoho, Brevo SMTP…) works the same way.

## Two businesses: LUAZ and LUAZ Labs
The page starts with a **Business** selector: **LUAZ** (your Gmail sender) and **LUAZ Labs** (Zoho, info@luazwellness.de).
Each business is completely separate: its own sender, SMTP login, templates, daily inbox folder,
sent log and unsubscribe list (all inside `businesses/<name>/`).
 1. Pick the business -> tab **2 · Sender settings** -> check the preset, From email, From name, footer -> enter that
    mailbox's app password (Enter) -> **Save settings**.
 2. Tab **1 · Send** -> upload file, write message, Send test, Send to all.
 3. Need a third brand? Choose **➕ New business**.
Automatic mode: `python send_daily.py --business "LUAZ Labs" --template news`
(password via env var `MAILER_PASSWORD`).

## The Send tab: three steps, in any order
 1. **Message** - subject, text, attachments, signature. Works even before you choose anyone.
 2. **Recipients** - upload a file, pick a saved list, or type emails. Change them as often as you like: the message is never touched.
 3. **Review & send** - shows who gets what, a preview, **Send test** (works before recipients are chosen) and the final confirm.
Picked the wrong list? Just choose another one in step 2 - nothing has been sent until you tick the confirm box and press **Send to all**.

## Recipients: file, typed, or both
Tab 1 has a switch: **Upload file** / **Type or paste emails** / **Both**. Typed emails can be one per line or separated by
commas / semicolons, optionally with a name (`anna@example.com, Anna` or `Anna <anna@example.com>`).
`{Name}` is empty for addresses without a name.

## Writing the message (rich text, signature, attachments)
 - The message box is a real editor: **bold, italic, underline, colours, sizes, headings, bullet / numbered lists, links**, undo/redo,
   and a **+ Placeholder** menu (inserts `{Name}` etc.). Choose *Plain text* if you prefer.
 - **Signature** (tab 2, per business): write it once with the same editor, add an optional **logo** (shown under the text).
   It is added to every email; untick *Add my signature* on tab 1 to leave it out once.
 - **Attachments**: upload files from your computer and/or pick files from the Data folder. They go with every email
   (keep them small - big attachments often land in spam; Gmail / Zoho cap a message at roughly 20-25 MB).
 - Every rich email also contains an automatic plain-text version, and names / values are inserted safely.
 - *Preview for first recipient* shows exactly how it will look.

## Data folder (tab 4, one per business)
Each business has its own storage space: `businesses/<name>/data/`.
 - **Add** any files (contact lists, PDFs, images …), several at once; **download** or **delete** (asks to confirm) each file;
   **preview** CSV / Excel / text / images.
 - **Export all as ZIP** and **Import a ZIP** to back up or move a business's files.
 - **Use** them: on tab 1 choose *Saved list (Data folder)* as recipients, or tick files under *Attach files from the Data folder*
   to send them with every email. Typed email lists can be saved as a list too.
 - Command line: `python send_daily.py --business "LUAZ" --template news --attach brochure.pdf`

## Daily use (one click)
1. Tab **1 · Send**: drop in the morning CSV/Excel (or put it in the `inbox/` folder – newest file is used).
2. Pick the email column (auto-detected). The tool shows invalid / duplicate / unsubscribed counts.
3. Write subject + body. Use `{Name}`, `{Company}` … = any column header. Save as a template.
4. *Send test* → tick the confirm box → **Send to all**.

## Fully automatic (no clicking)
Save a template in the GUI, then schedule this command each morning:
    python send_daily.py --template newsletter
Set the password via environment variable `MAILER_PASSWORD`.
 - Windows: Task Scheduler;  Mac/Linux: cron (`0 9 * * * ...`).
 - `--dry-run` shows counts without sending.

## Safety built in
- Skips invalid, duplicate and unsubscribed addresses (list them in `unsubscribed.csv`, one per line).
- Skips anyone already mailed successfully today (so a double click can't double-send).
- Every send/fail is written to `sent_log.csv`. Password is never saved to disk.

## Important limits
- Gmail ≈ 500 mails/day (Workspace ≈ 2000). Above that, or for large marketing lists, use a
  transactional SMTP service (Brevo, Amazon SES, Mailgun) – only the SMTP settings change.
- Marketing mail to people who didn't opt in can violate GDPR / anti-spam law (you're in Germany: UWG §7
  requires consent). Include a real unsubscribe path and sender address in the footer, and honour requests.
- Cold bulk mail from a normal mailbox can land in spam; set up SPF/DKIM/DMARC on your own domain.
