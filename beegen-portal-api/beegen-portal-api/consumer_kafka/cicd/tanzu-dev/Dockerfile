FROM harbor-tanzu-dev.mbbank.com.vn/aicenter/nlp/python:3.12-beechat-apt

WORKDIR /app

ARG NEXUS_USER
ARG NEXUS_PASSWORD
ARG NEXUS_PYTHON_INDEX_URL
ARG NEXUS_PYTHON_TRUSTED_HOST

COPY requirements.txt /app/requirements.txt
COPY supervisord.conf /etc/supervisor/supervisord.conf

RUN pip install \
--no-cache-dir \
--no-build-isolation \
--progress-bar off \
-r /app/requirements.txt \
-i http://${NEXUS_USER}:${NEXUS_PASSWORD}@10.1.12.177:8445/repository/repo-pypi-host-beegen-core/simple \
--extra-index-url http://${NEXUS_USER}:${NEXUS_PASSWORD}@${NEXUS_PYTHON_INDEX_URL} \
--trusted-host ${NEXUS_PYTHON_TRUSTED_HOST}

COPY . .
RUN groupadd -r -g 10000 appadmin 
RUN useradd -m -d /home/appadmin/ -s /bin/bash -u 10000 -r -g appadmin appadmin
RUN chown -R appadmin:appadmin /app

# Set the default user. 
USER appadmin 
VOLUME /app
VOLUME /tmp
ENV PYTHONPATH=/app/src