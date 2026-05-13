FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    vainfo \
    libva2 \
    libva-drm2 \
    intel-media-va-driver \
    i965-va-driver \
    mesa-va-drivers \
    fonts-dejavu-core \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8080
CMD ["python", "/app/app.py"]
