# Chillify API and worker image.
#
# Every external tool is pinned to the exact version named in ARCHITECTURE
# section 2. FFmpeg is built from the upstream 8.1.2 release tarball, verified
# by checksum, because no distribution or third-party build publishes that
# exact version. SpotDL lives in its own isolated environment: it caps
# fastapi<0.104 and uvicorn<0.24, so it is never importable in this process
# and is invoked as an argument-vector subprocess.

# ---------------------------------------------------------------------------
# FFmpeg 8.1.2 — built from source, checksum-verified
# ---------------------------------------------------------------------------
FROM python:3.14.6-slim-trixie AS ffmpeg-build

ARG FFMPEG_VERSION=8.1.2
ARG FFMPEG_SHA256=464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential=12.12 \
        ca-certificates \
        curl \
        nasm \
        pkg-config \
        libmp3lame-dev \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL -o ffmpeg.tar.xz \
        "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
    && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
    && tar -xf ffmpeg.tar.xz --strip-components=1 \
    && rm ffmpeg.tar.xz

# Only the codecs Chillify actually uses: MP3 encode/decode plus probing.
# Network, autodetect, and every unused component stay out of the binary.
RUN ./configure \
        --prefix=/opt/ffmpeg \
        --disable-debug \
        --disable-doc \
        --disable-network \
        --disable-autodetect \
        --disable-ffplay \
        --enable-gpl \
        --enable-libmp3lame \
        --enable-small \
    && make -j"$(nproc)" \
    && make install \
    && /opt/ffmpeg/bin/ffmpeg -version | head -1

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.14.6-slim-trixie AS runtime

ARG UV_VERSION=0.11.29
ARG DENO_VERSION=2.9.3
ARG SPOTDL_VERSION=4.5.2

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    XDG_CACHE_HOME=/tmp/cache \
    HOME=/tmp \
    PATH="/opt/chillify/.venv/bin:/opt/ffmpeg/bin:/opt/deno/bin:${PATH}" \
    CHILLIFY_SPOTDL_BIN=/opt/spotdl/bin/spotdl \
    CHILLIFY_FFMPEG_BIN=/opt/ffmpeg/bin/ffmpeg \
    CHILLIFY_FFPROBE_BIN=/opt/ffmpeg/bin/ffprobe \
    CHILLIFY_YT_DLP_BIN=/opt/chillify/.venv/bin/yt-dlp \
    CHILLIFY_DENO_BIN=/opt/deno/bin/deno

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        libmp3lame0 \
        unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ffmpeg-build /opt/ffmpeg /opt/ffmpeg

# Pinned uv, used for both the application environment and the isolated
# SpotDL environment.
RUN curl -fsSL \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
        | tar -xz -C /tmp \
    && install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv \
    && rm -rf /tmp/uv-x86_64-unknown-linux-gnu \
    && uv --version

# Deno is SpotDL's JavaScript runtime. Pinning it keeps acquisition behavior
# reproducible instead of depending on whatever runtime happens to be present.
RUN mkdir -p /opt/deno/bin \
    && curl -fsSL -o /tmp/deno.zip \
        "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
    && unzip -q /tmp/deno.zip -d /opt/deno/bin \
    && rm /tmp/deno.zip \
    && chmod 0755 /opt/deno/bin/deno \
    && deno --version

# SpotDL in its own environment. Nothing here is importable by the API or
# worker process; the only coupling is the subprocess argument/output contract.
RUN uv venv /opt/spotdl \
    && VIRTUAL_ENV=/opt/spotdl uv pip install "spotdl==${SPOTDL_VERSION}" \
    && /opt/spotdl/bin/spotdl --version

WORKDIR /opt/chillify

COPY backend/pyproject.toml backend/uv.lock backend/alembic.ini ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/src ./src
COPY backend/migrations ./migrations
RUN uv sync --locked --no-dev

# The application reads mounted roots and writes nothing into the image.
RUN chmod -R a+rX /opt/chillify /opt/ffmpeg /opt/deno /opt/spotdl

EXPOSE 8000

CMD ["uvicorn", "chillify.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
