# VTU and BMSIT workspace: accounts and developer access

This is a local Windows application for BMSIT, based on the user's statement that
the college sets its internal and semester-end papers. This is not a claim of
official affiliation or verification of a particular paper structure.

## Start

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,app]"
.\.venv\Scripts\python.exe -m api.server
```

Open `http://127.0.0.1:8001`. The old static server on port 8000 cannot handle
accounts. Use the account server for the new UI. Keep it bound to loopback.

Create your account with your name, email, and a password. Email is an account
identifier; there is no email delivery, verification, OTP, Google sign-in, or
password-recovery service. Profile editing currently supports display name and
password changes. Account data and imported files remain in ignored `data/`.

## Developer access

New signups always receive the regular user role. There is no default password,
no special email shortcut, and no developer role selector in the browser. After
creating your own account, run this locally with your account's actual email:

```powershell
.\.venv\Scripts\python.exe -m scripts.grant_developer --email "your-email@example.com"
```

Click the avatar to open your profile, then refresh it. Developer studio appears
only for the developer role. Both developer API endpoints also check that role;
hiding a link is not the access-control mechanism.

## Dataset history and success rates

The current workflow supports separate VTU and BMSIT collections, separate login
pages for users and developers, PDF source attachments and prospective evaluation.
See [DATA_WORKFLOW.md](DATA_WORKFLOW.md) for the exact upload and scoring steps.

Use `/#login` for user accounts and `/#developer-login` after a local developer
role grant. Ordinary accounts can read both institutions' transcribed papers and
source PDFs; developer upload, history and prediction APIs remain role-protected.

A saved prediction is scored when its matching reviewed target arrives. Results
use all listed question marks, not an assumed official maximum. M2 rolling-origin
backtesting is still pending. Email verification, recovery and PDF OCR are also
not implemented. All signed-in accounts share the college subject collections;
per-student enrollment or private collections are not implemented.

## Security and deployment boundary

Passwords use salted scrypt; sessions use random opaque tokens, stored hashed in
SQLite and sent as HttpOnly, SameSite=Strict cookies. Password changes invalidate
all the account's sessions. Mutation requests require a same-origin request header;
foreign origins are rejected. Authentication requests are limited per client IP,
and JSON body size is bounded. No passwords or tokens are stored in localStorage.

The cookie is not Secure because this preview runs on loopback HTTP. Hosted use
requires HTTPS, Secure cookies, a production database, verified email delivery,
recovery, and deployment review. SQLite state makes this implementation unsuitable
for serverless hosting as-is. Do not publish the current account server.

Implementation references:
- [Python password derivation documentation](https://docs.python.org/3/library/hashlib.html#key-derivation)
- [FastAPI password hashing guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)

The original `web/app.js` is retained as an unloaded legacy prototype. The HTML
now loads `workspace.js`, which obtains all collection counts from the server and
does not display the old hardcoded performance values.
