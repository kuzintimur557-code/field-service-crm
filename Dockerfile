FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /srv/app

COPY requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /srv/app

RUN useradd --create-home app \
    && mkdir -p /data \
    && chown -R app:app /data /srv/app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
