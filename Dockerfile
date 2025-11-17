# Dockerfile

FROM python:3.10-slim

# install deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy source
COPY . .

# expose port only for health (not necessary but ok)
EXPOSE 8080

# run worker
CMD ["python", "worker.py"]
