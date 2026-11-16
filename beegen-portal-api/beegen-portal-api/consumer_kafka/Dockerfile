FROM k8sdev.mbbank.com.vn/common/python:3.12.7

ARG NEXUS_USER
ARG NEXUS_PASSWORD
ARG NEXUS_PYTHON_INDEX_URL
ARG NEXUS_PYTHON_TRUSTED_HOST

#Set up web app
WORKDIR /cua-document-consumer
COPY ./requirements.txt /cua-document-consumer/requirements.txt
COPY supervisord.conf /etc/supervisor/supervisord.conf
RUN pip3 install -r /cua-document-consumer/requirements.txt \
    -i http://${NEXUS_USER}:${NEXUS_PASSWORD}@${NEXUS_PYTHON_INDEX_URL} \
    --trusted-host ${NEXUS_PYTHON_TRUSTED_HOST}

COPY ./app /cua-document-consumer/app
ENV PYTHONPATH=/cua-document-consumer/app

# Create a group and user
RUN addgroup --system --gid 10000 appadmin
RUN adduser --system --uid 10000 --group appadmin
RUN chown -R appadmin:appadmin /cua-document-consumer
USER appadmin
VOLUME /cua-document-consumer
