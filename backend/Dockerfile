FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies from placeholder packages first, so that editing source code
# does not invalidate this slow layer.
COPY pyproject.toml ./
RUN mkdir app scheduler \
    && touch app/__init__.py scheduler/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

COPY . .

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
