#!/bin/sh
# Start script for hosts that cannot build images (e.g. Hostinger Docker Manager).
# Runs in the plain python:3.12-slim image: fetches this repository and rmapi, installs, starts the planner.
set -eu

GIT_REPO="${GIT_REPO:-mgasser/remarkable-calendar}"
GIT_REF="${GIT_REF:-main}"
export GIT_REPO GIT_REF DATA_DIR="${DATA_DIR:-/data}" PYTHONUNBUFFERED=1

echo "bootstrap: fetching ${GIT_REPO}@${GIT_REF} and rmapi"
python - <<'EOF'
import hashlib, io, os, platform, shutil, tarfile, urllib.error, urllib.request

repo, ref = os.environ["GIT_REPO"], os.environ["GIT_REF"]

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()

# 1) Source code (branch, then tag/commit)
for url in (f"https://github.com/{repo}/archive/refs/heads/{ref}.tar.gz", f"https://github.com/{repo}/archive/{ref}.tar.gz"):
    try:
        blob = get(url)
        break
    except urllib.error.HTTPError:
        continue
else:
    raise SystemExit(f"bootstrap: cannot download {repo}@{ref}")
shutil.rmtree("/app", ignore_errors=True)
with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
    root = tar.getmembers()[0].name.split("/")[0]
    tar.extractall("/tmp/src", filter="data")
shutil.move(f"/tmp/src/{root}", "/app")

# 2) rmapi, pinned and checksum-verified
version = "v0.0.35"
sums = {"amd64": "117616151d11937446ead6972b0934f97155443087f8406141db38fd1ac8fb25",
        "arm64": "645c170d8119b4dcb652cf79612e362fcb032dc0e5869ff520eec1324da39637"}
arch = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]
blob = get(f"https://github.com/ddvk/rmapi/releases/download/{version}/rmapi-linux-{arch}.tar.gz")
if hashlib.sha256(blob).hexdigest() != sums[arch]:
    raise SystemExit("bootstrap: rmapi checksum mismatch")
with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
    with open("/usr/local/bin/rmapi", "wb") as out:
        out.write(tar.extractfile("rmapi").read())
os.chmod("/usr/local/bin/rmapi", 0o755)
print("bootstrap: source and rmapi", version, "ready")
EOF

if [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf ]; then
  (apt-get update -qq && apt-get install -y -qq --no-install-recommends fonts-dejavu-core >/dev/null) \
    || echo "bootstrap: fonts-dejavu-core not installed, falling back to Courier"
fi

pip install --no-cache-dir --disable-pip-version-check -q --root-user-action=ignore -r /app/requirements.txt
mkdir -p "$DATA_DIR"
cd /app
[ "$#" -gt 0 ] || set -- serve
exec python -m planner "$@"
