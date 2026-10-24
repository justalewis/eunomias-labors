FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Submissions AND the generated coverage table live on the mounted volume, so a
# deploy doesn't discard them and the nightly refresh writes where the app reads.
ENV EUNOMIA_DATA=/data     EUNOMIA_DB=/data/submissions.sqlite3
VOLUME ["/data"]

EXPOSE 8080

# Two workers is plenty for a four-page site; the only write path is one INSERT.
# Seed the volume from the image on first boot, so a fresh deploy is never blank.
CMD ["sh", "-c", "cp -n /app/data/coverage.json /data/coverage.json 2>/dev/null; exec gunicorn --bind 0.0.0.0:8080 --workers 2 --timeout 30 app:app"]
