# NaturalShot en el navegador: la app de escritorio corre acá y Xpra muestra su pantalla en una pestaña.
# Se construye desde la raíz del repositorio (docker-compose.yml: context ..).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=es_AR.UTF-8 LC_ALL=es_AR.UTF-8 TZ=America/Argentina/Buenos_Aires \
    HOME=/root QT_QPA_PLATFORM=xcb XDG_RUNTIME_DIR=/tmp/xdg

# Xpra desde su repositorio oficial: el servidor, su parte X11 (sin ella no arranca), los códecs y el cliente HTML5;
# después Python y las librerías gráficas de Qt.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget gnupg locales tzdata \
    && sed -i 's/# es_AR.UTF-8/es_AR.UTF-8/' /etc/locale.gen && locale-gen \
    && wget -qO /usr/share/keyrings/xpra.asc https://xpra.org/xpra.asc \
    && wget -qO /etc/apt/sources.list.d/xpra.sources \
         https://raw.githubusercontent.com/Xpra-org/xpra/master/packaging/repos/noble/xpra.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
         xpra-server xpra-x11 xpra-codecs xpra-html5 xvfb xauth dbus-x11 \
         python3 python3-venv python3-pip \
         libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
         libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libfontconfig1 libdbus-1-3 \
         fonts-dejavu fonts-liberation fonts-noto-color-emoji xdg-utils evince \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY . .

# Las carpetas que se ven desde el portal: Entradas (lo que sube la persona) y Exportados (lo que guarda).
RUN mkdir -p /root/NaturalShot/Entradas /root/NaturalShot/Exportados /tmp/xdg && chmod 700 /tmp/xdg \
    && printf '#!/bin/sh\n# Si cierran la ventana de NaturalShot, se vuelve a abrir sola.\ncd /root/NaturalShot\nwhile true; do /opt/venv/bin/python /app/main.py; sleep 2; done\n' > /usr/local/bin/naturalshot-bucle \
    && chmod +x /usr/local/bin/naturalshot-bucle

EXPOSE 14500
CMD ["xpra", "start", ":100", "--daemon=no", "--bind-tcp=0.0.0.0:14500", "--html=on", \
     "--start-child=/usr/local/bin/naturalshot-bucle", "--exit-with-children=no", \
     "--pulseaudio=no", "--notifications=no", "--webcam=no", "--mdns=no", "--printing=no", \
     "--file-transfer=yes", "--clipboard=yes", "--speaker=off", "--microphone=off"]
