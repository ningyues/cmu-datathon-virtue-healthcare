FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/carelens
COPY requirements.txt ./
COPY agents/requirements.txt agents/requirements.txt
COPY app/requirements.txt app/requirements.txt
COPY virtue-healthcare/requirements.txt virtue-healthcare/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ agents/
COPY app/ app/
COPY pipeline/ pipeline/
COPY virtue-healthcare/app/ virtue-healthcare/app/
COPY virtue-healthcare/db/ virtue-healthcare/db/
COPY data/processed/ data/processed/
COPY --from=frontend-build /build/frontend/dist frontend/dist/
RUN useradd --system --uid 10001 carelens
USER carelens
EXPOSE 8000
CMD ["python", "-m", "app.api", "--host", "0.0.0.0"]
