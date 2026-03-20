# =============================================================================
# 🐳 DOCKERFILE - SCRAPING-SERVICE (Production-Ready)
# =============================================================================
# Service: Scraping Marakhib Business (FastApi + Python 3.11)
# Docker Hub: marakhib/mb-scraping-service
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 1: BUILD
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

# Variables d'environnement pour optimisation
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1

# Installer Poetry pour gestion des dépendances
RUN pip install poetry

# Working directory
WORKDIR /app

# Copier requirements.txt d'abord pour le cache
COPY requirements.txt .

# Installer les dépendances dans un virtualenv
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# -----------------------------------------------------------------------------
# STAGE 2: RUNTIME
# -----------------------------------------------------------------------------
FROM python:3.11-slim as runtime

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# -------------------------------------------------------------------------
# SÉCURITÉ: Créer utilisateur non-root
# -------------------------------------------------------------------------
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2 \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# -------------------------------------------------------------------------
# Copier les dépendances depuis le builder
# -------------------------------------------------------------------------
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copier le code de l'application
COPY app/ ./app/

# -------------------------------------------------------------------------
# Permissions
# -------------------------------------------------------------------------
RUN chown -R appuser:appgroup /app

# -------------------------------------------------------------------------
# Switch vers utilisateur non-root
# -------------------------------------------------------------------------
USER appuser

# -------------------------------------------------------------------------
# PORT & HEALTHCHECK
# -------------------------------------------------------------------------
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# -------------------------------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
