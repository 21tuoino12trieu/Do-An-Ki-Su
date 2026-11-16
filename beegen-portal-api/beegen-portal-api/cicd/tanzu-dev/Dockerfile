FROM harbor-tanzu-dev.mbbank.com.vn/aicenter/nlp/python:3.12-beechat-apt

WORKDIR /app

ARG NEXUS_USER
ARG NEXUS_PASSWORD
ARG NEXUS_PYTHON_INDEX_URL
ARG NEXUS_PYTHON_TRUSTED_HOST

# ===== CẤU HÌNH MÔI TRƯỜNG & FIX READ-ONLY FS =====
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache
ENV PIP_NO_CACHE_DIR=1

# Trỏ đường dẫn webdriver mặc định nếu cần
ENV CHROMEDRIVER_PATH=/tmp/chromedriver 

COPY requirements.txt /app/requirements.txt

RUN pip install \
    --no-cache-dir \
    --no-build-isolation \
    --progress-bar off \
    -r /app/requirements.txt \
    -i http://${NEXUS_USER}:${NEXUS_PASSWORD}@10.1.12.177:8445/repository/repo-pypi-host-beegen-core/simple \
    --extra-index-url http://${NEXUS_USER}:${NEXUS_PASSWORD}@${NEXUS_PYTHON_INDEX_URL} \
    --trusted-host ${NEXUS_PYTHON_TRUSTED_HOST}

ENV BEEGEN_RESOURCE_HUB_SECRET=aicenter

COPY . .
COPY supervisord.conf /etc/supervisor/supervisord.conf

RUN cp /app/cicd/tanzu-dev/DC02/configmap-k8s/config.env /app/.env && \
    cp /app/cicd/tanzu-dev/DC02/configmap-k8s/beeflow.yaml /app/config/beeflow.yaml && \
    cp /app/cicd/tanzu-dev/DC02/configmap-k8s/kafka.yaml /app/config/kafka.yaml

RUN groupadd -r -g 10000 appadmin && \
    useradd -m -d /home/appadmin/ -s /bin/bash -u 10000 -r -g appadmin appadmin && \
    chown -R appadmin:appadmin /app

# Set the default user. 
USER appadmin 

ENV PYTHONPATH=/app/src

VOLUME /app /tmp