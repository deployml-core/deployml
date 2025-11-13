FROM grafana/grafana:10.2.0

# Switch to root to install and configure
USER root

# Create directories first
RUN mkdir -p /etc/grafana/provisioning/dashboards && \
    mkdir -p /etc/grafana/provisioning/datasources && \
    mkdir -p /var/lib/grafana/dashboards

# Copy dashboard configurations
COPY dashboards/ /etc/grafana/provisioning/dashboards/
COPY datasources/ /etc/grafana/provisioning/datasources/
COPY dashboard-definitions/ /var/lib/grafana/dashboards/

# Set proper ownership (grafana user is UID 472 in the official image)
RUN chown -R 472:472 /etc/grafana/provisioning /var/lib/grafana/dashboards

# Switch back to grafana user
USER 472

# Expose Grafana port
EXPOSE 3000

# Grafana will use default entrypoint

