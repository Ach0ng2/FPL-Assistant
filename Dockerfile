# Gunakan base image Python 3.12 slim yang sangat ringan
FROM python:3.12-slim

# Install uv untuk manajemen dependensi super cepat
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml uv.lock ./

# Install dependensi project tanpa build package
RUN uv pip install --no-cache -r pyproject.toml

# Copy seluruh source code
COPY . .

# Install fpl-assistant sebagai local package
RUN uv pip install --no-cache -e .

# Perintah default: jalankan bot Telegram interaktif
CMD ["fpl-assistant", "bot"]
