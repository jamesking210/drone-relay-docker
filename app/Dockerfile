FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LIBVA_DRIVER_NAME=iHD

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    fonts-dejavu-core \
    curl \
    ca-certificates \
    vainfo \
    libva2 \
    libva-drm2 \
    libva-x11-2 \
    && (apt-get install -y --no-install-recommends intel-media-va-driver || true) \
    && (apt-get install -y --no-install-recommends intel-media-va-driver-non-free || true) \
    && (apt-get install -y --no-install-recommends i965-va-driver || true) \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8080

CMD ["python", "main.py"]
