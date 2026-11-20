FROM python:3.12-slim

# rmapi talks to the reMarkable Cloud (https://github.com/ddvk/rmapi, AGPL-3.0)
ARG RMAPI_VERSION=v0.0.35
ARG RMAPI_SHA256_AMD64=117616151d11937446ead6972b0934f97155443087f8406141db38fd1ac8fb25
ARG RMAPI_SHA256_ARM64=645c170d8119b4dcb652cf79612e362fcb032dc0e5869ff520eec1324da39637
ARG TARGETARCH=amd64

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl fonts-dejavu-core tzdata \
 && case "$TARGETARCH" in \
      amd64) SUM="$RMAPI_SHA256_AMD64" ;; \
      arm64) SUM="$RMAPI_SHA256_ARM64" ;; \
      *) echo "unsupported arch $TARGETARCH" && exit 1 ;; \
    esac \
 && curl -fsSL -o /tmp/rmapi.tgz "https://github.com/ddvk/rmapi/releases/download/${RMAPI_VERSION}/rmapi-linux-${TARGETARCH}.tar.gz" \
 && echo "$SUM  /tmp/rmapi.tgz" | sha256sum -c - \
 && tar -xzf /tmp/rmapi.tgz -C /usr/local/bin rmapi \
 && chmod 755 /usr/local/bin/rmapi \
 && rm /tmp/rmapi.tgz \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY planner ./planner

RUN useradd --create-home --uid 1000 planner && mkdir -p /data && chown planner /data
USER planner

ENV TZ=Europe/Zurich \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

HEALTHCHECK --interval=30m --timeout=30s --start-period=10m CMD ["python", "-m", "planner", "healthcheck"]
ENTRYPOINT ["python", "-m", "planner"]
CMD ["serve"]
