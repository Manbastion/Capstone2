# Publish the notification update

The feature is based on `b324d66` (15 October 2026). Its code, docs, demo and tests
are prepared locally. Creating a remote feature branch through the connected
GitHub app returned **403: Resource not accessible by integration**. No branch,
commit or pull request was published by that attempt.

## Give the connected app repository access

Your personal permission to push and a GitHub app's permission are separate.
The owner of **Manbastion/Capstone2** should review the connected GitHub app's
installation under GitHub **Settings → Applications → Installed GitHub Apps →
Configure**, grant it access to Capstone2 and approve the permissions the app
requests for repository contents and pull requests. An installation limited to
a different account's repositories does not grant access here.

The included `.github/workflows/notification-tests.yml` may also require the
app's workflow-writing permission. If that is unavailable, the repository owner
can add that CI file separately. Do not post a token in chat. After access is
updated, the assistant can retry creating `feature/notification-polish` and a
reviewable pull request.

See GitHub's [app installation guide](https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party)
and [permission explanation](https://docs.github.com/en/apps/using-github-apps/authorizing-github-apps).

## Alternatively push from your own computer

The download contains a complete project and **notification-update.patch**.
Use a fresh clone to avoid mixing the update with unrelated edits:

```bash
git clone https://github.com/Manbastion/Capstone2.git Capstone2-review
cd Capstone2-review
git switch -c feature/notification-polish
git apply --check "/full/path/to/notification-update.patch"
git apply "/full/path/to/notification-update.patch"
python3 -m unittest discover -s tests -v
python3 tools/check_rhino_syntax.py
git add .
git commit -m "Restore and polish desktop and ntfy completion notifications"
git push -u origin feature/notification-polish
```

On Windows use the appropriate `py -3` command for the Python checks. Git will
use your normal account authentication. If `git apply --check` reports a conflict,
stop and reconcile changes made after b324d66; do not overwrite newer team edits.
After pushing, open a pull request from the feature branch into main.

Do not upload personal settings, phone tokens, logs, demo run folders, backup
files or changed transfer history. The patch contains only the intended source,
documentation, tests, launchers, CI configuration and synthetic examples.

## Suggested review focus

- Current component 02 and its included adapter send after validated export,
  independently of Check, and never change calculation success on delivery failure.
- Component 04 latches final loop signals; run/loop scope prevents per-iteration spam.
- Phone setup is opt-in; request/response validation and bounded retries are covered.
- Current transfer support for strings/arrays and JSON is preserved.
- The README and setup guides use the current root layout; old nested integration
  instructions and embedded .gh code must be updated on test machines.
- Device/real-MATLAB acceptance remains explicitly recorded as pending in TESTING.md.
