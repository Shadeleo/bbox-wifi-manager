# L'application dialogue avec la box sur le réseau local : lancez le conteneur
# avec --network host, sinon 192.168.1.254 est injoignable depuis le conteneur.
#   docker build -t bbox-wifi-manager .
#   docker run --rm --network host --env-file .env -v "$PWD/data:/app/data" bbox-wifi-manager
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=5000

WORKDIR /app

COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY app/ ./app/
COPY run.py ./

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000
CMD ["python", "run.py"]
