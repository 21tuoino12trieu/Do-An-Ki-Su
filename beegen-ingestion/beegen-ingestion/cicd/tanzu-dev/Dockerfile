FROM harbor-tanzu-dev.mbbank.com.vn/aicenter/nlp/python:3.12-beechat

ARG NEXUS_USER
ARG NEXUS_PASSWORD
ARG NEXUS_PYTHON_INDEX_URL
ARG NEXUS_PYTHON_TRUSTED_HOST

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt


ARG SERVICE_VERSION=1.0.0
RUN pip install --no-cache-dir \
--no-python-version-warning \
--progress-bar off \
-r /app/requirements.txt \
-i http://${NEXUS_USER}:${NEXUS_PASSWORD}@10.1.12.177:8445/repository/repo-pypi-host-beegen-core/simple \
--extra-index-url http://${NEXUS_USER}:${NEXUS_PASSWORD}@${NEXUS_PYTHON_INDEX_URL} \
--trusted-host ${NEXUS_PYTHON_TRUSTED_HOST}

ENV BEEGEN_RESOURCE_HUB_SECRET=aicenter
ENV HOME=/tmp

COPY . /app
COPY ./cicd/tanzu-dev/beeflow.yaml /app/config/beeflow.yaml
COPY ./cicd/tanzu-dev/config.env /app/.env

# Create a group and user
RUN addgroup --system --gid 10000 appadmin && \
    adduser --system --uid 10000 --group appadmin && \
    chown -R appadmin:appadmin /app

# Set the default user.
USER appadmin

VOLUME /tmp /app