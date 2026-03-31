FROM grafana/grafana:10.4.5

# Switch to root to copy files and change permissions
USER root

# Configure Grafana to listen on Cloud Run's expected port
ENV GF_SERVER_HTTP_PORT=8080 \
    GF_SECURITY_ADMIN_USER=admin \
    GF_SECURITY_ADMIN_PASSWORD=admin

# Copy entrypoint script and set permissions 
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

# Create provisioning directories
RUN mkdir -p /etc/grafana/provisioning/datasources \
    /etc/grafana/provisioning/dashboards

# Switch back to the default grafana user for runtime
USER grafana

# Set custom entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]