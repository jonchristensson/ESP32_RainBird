"""Block commits that would publish credentials or personal data.

Run by .githooks/pre-commit (staged changes, author identity) and
.githooks/commit-msg (the commit message). Can also be run by hand:

    python .githooks/check_private.py --tree        # every tracked file

Findings report file, line and rule only, never the matched text, so the
output is safe to show in a terminal or an agent transcript.

Besides generic patterns, two gitignored sources supply literal values:
  secrets.py         string values are parsed (not imported) and blocked
  .private-patterns  one literal per line, case-insensitive, # for comments
"""
import ast
import re
import subprocess
import sys
from pathlib import Path


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout


ROOT = Path(git("rev-parse", "--show-toplevel").strip())

# Paths that must never be committed, even with `git add -f`.
FORBIDDEN_PATH = re.compile(
    r"(^|/)secrets\.py$|(^|/)\.private-patterns$|(^|/)\.env$|\.log$"
    r"|^CLAUDE\.md$|^work/|^\.claude/"
)

# Values the docs use on purpose.
PLACEHOLDER_NUMBERS = {"36.4620", "-116.8666"}
ALLOWED_IPS = {"192.168.4.1"}  # WebREPL AP-mode default
ALLOWED_EMAIL = re.compile(
    r"(@users\.noreply\.github\.com|^noreply@anthropic\.com|@example\.(com|org|net)"
    r"|^git@github\.com)$",
    re.I,
)

SECRET_RULES = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("Apps Script deployment ID", re.compile(r"\bAKfyc[0-9A-Za-z_-]{20,}")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}")),
    ("API key (sk-)", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}")),
    ("32-char hex key", re.compile(r"\b[a-f0-9]{32}\b")),
]
PRECISE_NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}\.\d{4,}(?![\w.])")
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"
)
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def load_literals():
    """Return [(rule_name, literal, case_sensitive)] from the private sources."""
    literals = []
    secrets = ROOT / "secrets.py"
    if secrets.exists():
        tree = ast.parse(secrets.read_text(encoding="utf-8", errors="replace"))
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                continue
            name = getattr(node.targets[0], "id", "?")
            value = node.value.value.strip()
            if len(value) < 4 or "YOUR_" in value or value in {"0.0", "-0.0"}:
                continue
            rule = f"value of {name} from secrets.py"
            if name == "GOOGLE_SHEETS_URL":
                m = re.search(r"/macros/s/([^/]+)/", value)
                if m:
                    literals.append((rule, m.group(1), True))
                continue
            literals.append((rule, value, True))
            if name in ("LATITUDE", "LONGITUDE") and "." in value:
                whole, frac = value.split(".", 1)
                literals.append((rule + " (rounded)", f"{whole}.{frac[:3]}", True))
    patterns = ROOT / ".private-patterns"
    if patterns.exists():
        for line in patterns.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                literals.append(("entry in .private-patterns", line.lower(), False))
    return literals


def check_line(text, literals, is_pem=False):
    """Return the names of every rule the line breaks."""
    hits = []
    lowered = text.lower()
    for rule, literal, case_sensitive in literals:
        if (literal in text) if case_sensitive else (literal in lowered):
            hits.append(rule)
    for rule, pattern in SECRET_RULES:
        if pattern.search(text) and not (is_pem and rule != "private key"):
            hits.append(rule)
    if is_pem:
        return hits
    if any(m.group(0) not in PLACEHOLDER_NUMBERS for m in PRECISE_NUMBER.finditer(text)):
        hits.append("precise coordinate-like number")
    if any(m.group(0) not in ALLOWED_IPS for m in PRIVATE_IP.finditer(text)):
        hits.append("private LAN IP address")
    if MAC.search(text):
        hits.append("MAC address")
    if any(not ALLOWED_EMAIL.search(m.group(0)) for m in EMAIL.finditer(text)):
        hits.append("non-noreply email address")
    return hits


def staged_lines():
    """Yield (path, line_number, text) for every line added in the index."""
    diff = git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff", "--diff-filter=ACMR")
    path, lineno = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            yield path, lineno, line[1:]
            lineno += 1


def check_staged(literals):
    findings = []
    for path in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines():
        if FORBIDDEN_PATH.search(path):
            findings.append(f"{path}: file must never be committed")
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        m = re.search(r"<([^>]*)>", git("var", var))
        if m and not ALLOWED_EMAIL.search(m.group(1)):
            findings.append(f"{var}: email is not a GitHub noreply address "
                            "(git config user.email <id>+<user>@users.noreply.github.com)")
    for path, lineno, text in staged_lines():
        for rule in check_line(text, literals, path.endswith(".pem")):
            findings.append(f"{path}:{lineno}: {rule}")
    return findings


def check_message(msg_file, literals):
    findings = []
    text = Path(msg_file).read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("# ------------------------ >8"):
            break
        if line.startswith("#"):
            continue
        for rule in check_line(line, literals):
            findings.append(f"commit message:{lineno}: {rule}")
    return findings


def check_tree(literals):
    findings = []
    for path in git("ls-files").splitlines():
        if FORBIDDEN_PATH.search(path):
            findings.append(f"{path}: file must never be committed")
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for rule in check_line(line, literals, path.endswith(".pem")):
                findings.append(f"{path}:{lineno}: {rule}")
    return findings


def main():
    literals = load_literals()
    if len(sys.argv) == 3 and sys.argv[1] == "--message":
        findings = check_message(sys.argv[2], literals)
    elif sys.argv[1:] == ["--tree"]:
        findings = check_tree(literals)
    else:
        findings = check_staged(literals)
    if not findings:
        return 0
    print("Private-data check FAILED. Remove these before committing:", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print("Use placeholders (Furnace Creek coordinates, <device_ip>, <OTA_PASSWORD>).",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
