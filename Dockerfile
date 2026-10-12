# Dockerfile for Odoo 20.0 — production deployment image.
#
# Targets Ubuntu 24.04 LTS (Noble) since `requirements.txt` pins most
# Python packages to their Noble-era versions. PostgreSQL 16 (matching
# MIN_PG_VERSION in `odoo/release.py`) runs in a sibling container;
# this image only ships the Odoo server + Python dependencies.
#
# Build:   docker build -t odoo:20.0 .
# Run:     see docker-compose.yml

FROM ubuntu:24.04

LABEL maintainer="Odoo" \
      org.opencontainers.image.title="Odoo" \
      org.opencontainers.image.version="20.0" \
      org.opencontainers.image.source="https://github.com/odoo/odoo" \
      org.opencontainers.image.licenses="LGPL-3"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    ODOO_VERSION=20.0

# ---------------------------------------------------------------------------
# System dependencies (run as root)
#
# - postgresql-client: `psql` for health-checks & one-off DB ops from inside
#   the container.
# - python3 + pip: Noble ships Python 3.12, the MIN supported by Odoo 20.0.
# - libpq-dev, libxml2-dev, libxslt1-dev, libldap2-dev, libsasl2-dev,
#   libjpeg-dev, zlib1g-dev, libfreetype-dev, liblcms2-dev, libwebp-dev,
#   libtiff-dev: needed to build psycopg2, lxml, Pillow, python-ldap.
# - nodejs, npm, yarn: required only by addons that ship frontend assets
#   (e.g. `web/`, `web_studio/`). Assets are not built in this image; add
#   these back only if you need to bundle JS from scratch.
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dirmngr \
        gnupg \
        less \
        locales \
        postgresql-client \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        python3-wheel \
        build-essential \
        pkg-config \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libldap2-dev \
        libsasl2-dev \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype-dev \
        liblcms2-dev \
        libwebp-dev \
        libtiff-dev \
        libfontconfig1 \
        libssl-dev \
        xz-utils \
        vim-tiny \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8

# ---------------------------------------------------------------------------
# Create `odoo` user
#
# `chown` is *not* recursive: `/opt/odoo` is empty at this point, so the
# metadata change is O(1). All subsequent COPY/RUN install steps run as
# USER odoo, so venv and source end up owned by odoo for free — no giant
# `chown -R` over the entire tree afterwards (which is painfully slow on
# overlayfs when the tree has 50k+ files).
# ---------------------------------------------------------------------------
RUN groupadd -r odoo && useradd -r -g odoo -d /opt/odoo -s /bin/bash odoo \
    && mkdir -p /opt/odoo /var/lib/odoo /etc/odoo /var/log/odoo \
    && chown odoo:odoo /opt/odoo /var/lib/odoo /etc/odoo /var/log/odoo

# ---------------------------------------------------------------------------
# Switch to odoo for the rest of the build
#
# `env python3` will now resolve to the venv's interpreter (PATH puts the
# venv bin first). PYTHONPATH is belt-and-braces in case some sub-process
# still spawns the system python.
# ---------------------------------------------------------------------------
USER odoo
ENV PATH="/opt/odoo/venv/bin:/opt/odoo:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/opt/odoo/venv/lib/python3.12/site-packages"

WORKDIR /opt/odoo

# Python venv + bootstrap tools
RUN python3 -m venv /opt/odoo/venv \
    && /opt/odoo/venv/bin/pip install --no-cache-dir --upgrade \
        pip \
        setuptools \
        wheel

# Odoo Python dependencies (installed into the venv)
COPY --chown=odoo:odoo requirements.txt /opt/odoo/requirements.txt
RUN /opt/odoo/venv/bin/pip install --no-cache-dir -r /opt/odoo/requirements.txt

# Odoo source — owns the bundle, the symlinks, and the runtime config
COPY --chown=odoo:odoo . /opt/odoo/src

# `/usr/local/bin/` is root-owned; temporarily flip back to root to drop
# the symlinks, then return to odoo.
USER root
RUN ln -sf /opt/odoo/src/odoo-bin /usr/local/bin/odoo-bin \
    && ln -sf /opt/odoo/src/odoo-bin /usr/local/bin/odoo \
    && chmod +x /opt/odoo/src/odoo-bin

USER odoo

COPY --chown=odoo:odoo odoo.conf.example /etc/odoo/odoo.conf.example
COPY --chown=odoo:odoo entrypoint.sh /usr/local/bin/entrypoint.sh

# ---------------------------------------------------------------------------
# Runtime configuration baked into the image
# ---------------------------------------------------------------------------
ENV ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_DATA_DIR=/var/lib/odoo/.local/share/Odoo \
    ODOO_LOGFILE=/var/log/odoo/odoo.log

VOLUME ["/var/lib/odoo", "/etc/odoo", "/var/log/odoo"]

EXPOSE 8069 8072

WORKDIR /opt/odoo/src

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# CMD is intentionally empty — `entrypoint.sh` decides whether to do
# first-run bootstrap (`odoo-bin -i base ...`) or normal start
# (`odoo-bin server`).
CMD []
