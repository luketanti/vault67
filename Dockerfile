FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements-dev.txt ./
RUN pip install --no-cache-dir .
COPY . .
RUN useradd --create-home vault67 && chmod +x /app/docker-entrypoint.sh && chown -R vault67:vault67 /app
ENTRYPOINT ["./docker-entrypoint.sh"]
USER vault67
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
