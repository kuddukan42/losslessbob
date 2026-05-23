FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Virtual framebuffer + VNC + noVNC
    xvfb x11vnc novnc websockify \
    # Qt6 / xcb runtime (required by PyQt6 pip wheels)
    libgl1 libglib2.0-0 libdbus-1-3 libegl1 \
    libfontconfig1 libfreetype6 \
    libx11-6 libx11-xcb1 libxext6 libxrandr2 libxi6 libxtst6 \
    libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxkbcommon-x11-0 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    # QtWebEngine (Chromium) runtime
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libgbm1 libasound2 \
    # SoX — spectrogram generation
    sox \
    # Misc
    ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

# Serve noVNC at / instead of /vnc.html
RUN ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DISPLAY=:1
ENV PYTHONUNBUFFERED=1
ENV QT_QPA_PLATFORM=xcb
# Chromium sandbox is unavailable in unprivileged containers
ENV QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage"

RUN chmod +x docker/entrypoint.sh

EXPOSE 6080

VOLUME ["/app/data"]

ENTRYPOINT ["docker/entrypoint.sh"]
