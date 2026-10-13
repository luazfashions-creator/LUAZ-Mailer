# LUAZ-Mailer

## Starting the app
### Mac

Why the warning appears: files downloaded from the internet carry a “quarantine” flag, so macOS asks before running a script you double-click. Remove the flag once and the warning stops:

xattr -dr com.apple.quarantine ~/Downloads/mailer_tool
chmod +x ~/Downloads/mailer_tool/start_mac_linux.command

Change ~/Downloads/mailer_tool to wherever you unzipped it. After that, double-clicking start_mac_linux.command works with no prompt.

If you don’t want to run those commands, open Terminal, type cd (with a space), drag the folder into the window, press Enter, then run bash start_mac_linux.command. Running it this way doesn’t trigger the warning.

### Windows

Why the warning appears: Windows SmartScreen shows “Windows protected your PC” for scripts from the internet. Any one of these fixes it:

Easiest: click More info → Run anyway when it appears.
Before unzipping: right-click the .zip → Properties → tick Unblock → OK, then extract.
PowerShell, after unzipping:
  Get-ChildItem -Recurse "C:\path\to\mailer_tool" | Unblock-File

Python must be installed with “Add python.exe to PATH” ticked. Download it from python.org.

VS Code (Mac or Windows)
File → Open Folder… and choose the mailer_tool folder.
Open the terminal with Ctrl+` (backtick).
First time only, set it up: Mac / Linux:
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

Windows (PowerShell):

   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
Every time, activate the environment (the same activate line as above) and start the app:
   streamlit run app.py

Your browser opens at http://localhost:8501. Stop it with Ctrl+C in the terminal.
