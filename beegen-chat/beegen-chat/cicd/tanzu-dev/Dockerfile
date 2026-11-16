FROM harbor-tanzu-dev.mbbank.com.vn/aicenter/nlp/python:3.12-beechat

COPY . /app
WORKDIR /app

ARG NEXUS_USER
ARG NEXUS_PASSWORD
ARG NEXUS_PYTHON_INDEX_URL
ARG NEXUS_PYTHON_TRUSTED_HOST


ENV PIP_PROGRESS_BAR=off \
    PIP_NO_INPUT=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
    --no-python-version-warning \
    --progress-bar off \
    -r requirements.txt \
    -i http://${NEXUS_USER}:${NEXUS_PASSWORD}@${NEXUS_PYTHON_INDEX_URL} \
    --trusted-host ${NEXUS_PYTHON_TRUSTED_HOST}

ENV BEEGEN_RESOURCE_HUB_SECRET=aicenter
ENV MEM0_TELEMETRY=FALSE

RUN groupadd -r -g 10000 appadmin 
RUN useradd -m -d /home/appadmin/ -s /bin/bash -u 10000 -r -g appadmin appadmin
RUN chown -R appadmin:appadmin /app

# Set the default user. 
USER appadmin
VOLUME /app