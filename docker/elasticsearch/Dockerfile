# Debian 13 userspace. This tag is used instead of ubuntu/docker.elastic.co:
# those registries drop the manifest request from this network.
FROM postgres:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    until curl -fL --retry 5 --retry-all-errors --retry-delay 2 -C - \
      -o /tmp/elasticsearch.tar.gz \
      https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.15.3-linux-x86_64.tar.gz; \
    do \
      echo "elasticsearch archive download failed, retrying"; \
      sleep 3; \
    done; \
    tar -xzf /tmp/elasticsearch.tar.gz -C /usr/share; \
    rm /tmp/elasticsearch.tar.gz; \
    mv /usr/share/elasticsearch-8.15.3 /usr/share/elasticsearch

COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN groupadd --gid 1000 elasticsearch \
    && useradd --uid 1000 --gid 1000 --home-dir /usr/share/elasticsearch --shell /usr/sbin/nologin elasticsearch \
    && chmod 0755 /usr/local/bin/entrypoint.sh \
    && mkdir -p /usr/share/elasticsearch/data /usr/share/elasticsearch/logs \
    && chown -R elasticsearch:elasticsearch /usr/share/elasticsearch

USER elasticsearch
WORKDIR /usr/share/elasticsearch
EXPOSE 9200

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
