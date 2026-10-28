"""python -m detect.real_repos  ->  out/real_repos/<name>.json

Fetch each pinned public repo (shallow, exact commit) into .cache/repos/ and run the static scan.
The checkout is only read; nothing in it is built or executed.
"""

import json
import subprocess
from pathlib import Path

from contracts.manifest import new_run_id, utc_now

from .static_scan import scan

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / ".cache" / "repos"


def fetch(name: str, url: str, commit: str) -> Path:
    dest = CACHE / name
    if not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
        subprocess.run(["git", "remote", "add", "origin", url], cwd=dest, check=True)
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", commit], cwd=dest, check=True)
    subprocess.run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", "--force", commit], cwd=dest, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, check=True, capture_output=True, text=True).stdout.strip()
    if head != commit:
        raise RuntimeError(f"{name}: checked out {head}, expected pinned {commit}")
    return dest


def main():
    cfg = json.loads((REPO / "detect" / "real_repos.json").read_text())
    out_dir = REPO / "out" / "real_repos"
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in cfg["repos"]:
        result = scan(fetch(r["name"], r["url"], r["commit"]))
        result.update(run_id=new_run_id(), ts=utc_now(), url=r["url"], commit=r["commit"])
        (out_dir / f"{r['name']}.json").write_text(json.dumps(result, indent=1))
        print(f"{r['name']}@{r['commit'][:12]}: {result['files_scanned']} files, {result['summary']}")


if __name__ == "__main__":
    main()
