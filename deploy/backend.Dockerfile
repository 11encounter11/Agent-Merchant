FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8100

# 单 worker：checkpoint / 本地偏好 / 限流都以单实例为前提，不要用 --workers > 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1", "--proxy-headers"]
