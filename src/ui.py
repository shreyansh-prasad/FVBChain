"""
ui.py — Terminal UI helper for FaceID-Chain Verify.
All print formatting lives here; pipeline.py imports and uses these functions.
No external dependencies — only stdlib (sys, os, shutil).
"""
import os
import sys
import shutil

# ── Force UTF-8 on Windows so Unicode box characters render ──────────────────
if sys.platform == "win32":
    # Enable ANSI escape processing in cmd.exe / PowerShell
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError:
        pass  # Python < 3.7 fallback

_W = min(shutil.get_terminal_size((80, 24)).columns, 76)

# ── ANSI colour helpers ───────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR", ""))


def _a(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def bold(t: str) -> str:    return _a("1", t)
def dim(t: str) -> str:     return _a("2", t)
def green(t: str) -> str:   return _a("92", t)
def red(t: str) -> str:     return _a("91", t)
def yellow(t: str) -> str:  return _a("93", t)
def cyan(t: str) -> str:    return _a("96", t)
def magenta(t: str) -> str: return _a("95", t)
def gray(t: str) -> str:    return _a("90", t)
def white(t: str) -> str:   return _a("97", t)


# ── Layout ────────────────────────────────────────────────────────────────────

def _hr(char: str = "-") -> str:
    return char * (_W - 2)


def banner() -> None:
    print()
    print(cyan(bold("  +" + _hr("=") + "+")))
    print(cyan(bold("  |" + "  FaceID-Chain Verify".center(_W - 2) + "|")))
    print(cyan(bold("  |" + "Face Scan  ->  Web Search  ->  Blockchain".center(_W - 2) + "|")))
    print(cyan(bold("  +" + _hr("=") + "+")))
    print()
    print(dim(gray("  " + _hr())))
    print(dim(gray("  Input modes:")))
    print(dim(gray("    Webcam    ->  python src/pipeline.py")))
    print(dim(gray("    Image     ->  python src/pipeline.py --image photo.jpg")))
    print(dim(gray("    Clipboard ->  python src/pipeline.py --clipboard")))
    print(dim(gray("  " + _hr())))
    print()


def step_running(n: int, label: str) -> None:
    print(
        f"  {dim(gray('...'))}  {dim(gray(f'[{n}/6]'))}  {dim(gray(label))}",
        end="\r", flush=True
    )


def step_ok(n: int, label: str, detail: str = "") -> None:
    det = f"  {dim(gray(detail))}" if detail else ""
    print(f"  {green('[OK]')}  {dim(gray(f'[{n}/6]'))}  {bold(white(label))}{det}            ")


def step_fail(n: int, label: str, detail: str = "") -> None:
    det = f"  {dim(gray(detail))}" if detail else ""
    print(f"  {red('[!!]')}  {dim(gray(f'[{n}/6]'))}  {bold(red(label))}{det}            ")


def step_skip(n: int, label: str, detail: str = "") -> None:
    det = f"  {dim(gray(detail))}" if detail else ""
    print(f"  {yellow('[--]')}  {dim(gray(f'[{n}/6]'))}  {yellow(label)}{det}")


# ── Match results box ─────────────────────────────────────────────────────────

def matches_box(matches: list[dict]) -> None:
    print()
    if not matches:
        print(f"  {yellow('[!]')}  {yellow('No face matches found above threshold.')}")
        print(f"      {dim(gray('Try a higher-resolution or more frontal photo.'))}")
        print()
        return

    inner = _W - 4
    print(f"  {cyan('+' + '-' * inner + '+')}")
    title = f"  MATCHES FOUND ({len(matches)})  "
    print(f"  {cyan('|')}{bold(cyan(title.center(inner)[:inner]))}  {cyan('|')}")
    print(f"  {cyan('+' + '-' * inner + '+')}")

    for i, m in enumerate(matches, 1):
        pct = m.get("similarity_score", 0.0) * 100
        url = m.get("page_url", "")
        src = m.get("source", "")

        # Confidence colour and ASCII bar
        bar_filled = round(pct / 10)
        bar_empty  = 10 - bar_filled
        if pct >= 80:
            score_str = bold(green(f"{pct:.1f}%"))
            bar_str   = green("[" + "#" * bar_filled + "." * bar_empty + "]")
        elif pct >= 60:
            score_str = bold(yellow(f"{pct:.1f}%"))
            bar_str   = yellow("[" + "#" * bar_filled + "." * bar_empty + "]")
        else:
            score_str = yellow(f"{pct:.1f}%")
            bar_str   = yellow("[" + "#" * bar_filled + "." * bar_empty + "]")

        max_url = inner - 4
        url_disp = url if len(url) <= max_url else url[:max_url - 3] + "..."

        print(f"  {cyan('|')}")
        print(f"  {cyan('|')}  {bold(white(f'Match #{i}'))}  {score_str}  {bar_str}")
        print(f"  {cyan('|')}  {dim(gray('Profile :'))}  {cyan(url_disp)}")
        if src:
            print(f"  {cyan('|')}  {dim(gray('Source  :'))}  {dim(gray(src))}")

    print(f"  {cyan('+' + '-' * inner + '+')}")
    print()


# ── Blockchain record box ─────────────────────────────────────────────────────

def blockchain_box(record: dict) -> None:
    inner = _W - 4

    def row(label: str, value: str) -> None:
        max_v = inner - len(label) - 6
        v = value if len(value) <= max_v else value[:max_v - 3] + "..."
        print(f"  {magenta('|')}  {dim(gray(f'{label:<10}'))}  {cyan(v)}")

    print()
    print(f"  {magenta('+' + '-' * inner + '+')}")
    title = "  BLOCKCHAIN RECORD -- Ethereum Sepolia  "
    print(f"  {magenta('|')}{bold(magenta(title.center(inner)[:inner]))}  {magenta('|')}")
    print(f"  {magenta('+' + '-' * inner + '+')}")
    row("Tx Hash",   record.get("tx_hash", "—"))
    row("Explorer",  record.get("explorer_url", "—"))
    row("IPFS CID",  record.get("cid", "—"))
    print(f"  {magenta('+' + '-' * inner + '+')}")
    print()


# ── Footer ────────────────────────────────────────────────────────────────────

def success_footer() -> None:
    print(dim(gray("  " + _hr())))
    print(f"  {green(bold('[SUCCESS]'))}  {green('All 6 stages completed — pipeline done.')}")
    print(dim(gray("  " + _hr())))
    print()


def failure_footer(stage: int, reason: str) -> None:
    print()
    print(dim(gray("  " + _hr())))
    print(f"  {red(bold('[FAILED]'))}  Stopped at Stage {stage}.  {dim(gray(reason[:60]))}")
    print(dim(gray("  " + _hr())))
    print()
