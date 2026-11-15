# Image chỉ dùng xuất sơ đồ UML, không chạy Kafka broker.
FROM apache/kafka:4.1.2
USER root
RUN apk add --no-cache graphviz
USER 1000:1000
ENTRYPOINT ["java"]
