# Grafana Alloy — agente de telemetría para métricas y logs.
# Tag fijo (no :latest) para builds reproducibles y control de supply-chain.
# Verificar actualizaciones en: https://github.com/grafana/alloy/releases
FROM grafana/alloy:v1.8.3

COPY config.alloy /etc/alloy/config.alloy

# Crear el directorio de datos con ownership correcto ANTES de cambiar a nonroot.
# Sin esto, Alloy falla al arrancar: "mkdir data-alloy: permission denied".
RUN mkdir -p /var/lib/alloy && chown 65532:65532 /var/lib/alloy

EXPOSE 12345

# Correr como usuario sin privilegios — grafana/alloy expone UID 65532 (nonroot)
USER 65532:65532

ENTRYPOINT ["/bin/alloy", "run", "/etc/alloy/config.alloy", \
  "--server.http.listen-addr=0.0.0.0:12345", \
  "--storage.path=/var/lib/alloy"]
