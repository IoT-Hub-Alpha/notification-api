# Use official Python image
FROM python:3.13-slim

# Prevent Python from writing pyc files + enable stdout logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY app/ app/
COPY tests/ tests/
COPY scripts/ scripts/
COPY pytest.ini pytest.ini

# Expose port
EXPOSE 8015

WORKDIR /app

# Default command (dev server)
CMD ["python", "app/manage.py", "runserver", "0.0.0.0:8015"]