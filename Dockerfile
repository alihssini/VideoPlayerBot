FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# the Telegram login lives here: keep it in a volume and run `python login.py` once
# (docker run -it -v vpb-sessions:/app/sessions --env-file .env <image> python login.py)
VOLUME ["/app/sessions"]

CMD ["python", "main.py"]
