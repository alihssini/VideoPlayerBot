FROM python:3.12-slim

# ffmpeg with libass + fonts (Vazirmatn covers Persian / Arabic) for the lyrics videos
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fontconfig fonts-dejavu-core fonts-vazirmatn libfribidi0 libharfbuzz0b libraqm0 jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# the Telegram login lives here: keep it in a volume and run `python login.py` once
# (docker run -it -v vpb-sessions:/app/sessions --env-file .env <image> python login.py)
VOLUME ["/app/sessions", "/app/data"]

CMD ["python", "main.py"]
