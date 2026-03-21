# =============================================================================
# 🐳 DOCKERFILE - SCRAPING-SERVICE (Production-Ready)
# =============================================================================
# Service: Scraping Marakhib Business (FastApi + Python 3.11)
# Docker Hub: marakhib/mb-scraping-service
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 1: BUILD
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Variables d'environnement pour optimisation
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Working directory
WORKDIR /app

# -----------------------------------------------------------------------------
# COPIER LES FICHIERS DE DÉPENDANCES AVANT LE CODE
# -----------------------------------------------------------------------------
# Copier requirements.txt pour profiter du cache Docker
COPY requirements.txt ./

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# STAGE 2: RUNTIME
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

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
