#!/bin/bash
set -e

# Environment variables set by Cloud Run Job
WORKSPACE_NAME="${WORKSPACE_NAME}"
PROJECT_ID="${PROJECT_ID}"
REGION="${REGION}"

echo "🗑️  Starting teardown for workspace: ${WORKSPACE_NAME}"
echo "📋 Project: ${PROJECT_ID}, Region: ${REGION}"

# Find the bucket (it has a pattern: {project_id}-deployml-terraform-*)
BUCKET_NAME=$(gsutil ls | grep "${PROJECT_ID}-deployml-terraform-" | head -1 | xargs basename || echo "")

if [ -z "$BUCKET_NAME" ]; then
    echo "❌ Could not find deployml Terraform bucket"
    exit 1
fi

echo "📥 Downloading resource manifest from gs://${BUCKET_NAME}/${WORKSPACE_NAME}/resource-manifest.json"

# Download resource manifest
gsutil cp "gs://${BUCKET_NAME}/${WORKSPACE_NAME}/resource-manifest.json" /tmp/manifest.json || {
    echo "❌ Failed to download manifest"
    exit 1
}

# Use Python to parse JSON and delete resources (Python is available in cloud-sdk image)
python3 << PYTHON_EOF
import json
import subprocess
import sys

# Ensure output is flushed immediately
sys.stdout.flush()
sys.stderr.flush()

try:
    # Load manifest
    with open('/tmp/manifest.json', 'r') as f:
        manifest = json.load(f)
    
    resources = manifest.get('resources', {})
    project_id = manifest.get('project_id', '${PROJECT_ID}')
    region = manifest.get('region', '${REGION}')

    print("✅ Manifest downloaded. Found resources to delete:")
    sys.stdout.flush()
    for resource_type, items in resources.items():
        if items:
            print(f"  {resource_type}: {len(items)} items")
    sys.stdout.flush()

    # Set project
    subprocess.run(['gcloud', 'config', 'set', 'project', project_id], check=True)

    # Delete Cloud Run services
    if resources.get('cloud_run_services'):
        print("\n🗑️  Deleting Cloud Run services...")
        sys.stdout.flush()
        for service in resources['cloud_run_services']:
            name = service.get('name')
            svc_region = service.get('region', region)
            if name:
                print(f"  Deleting Cloud Run service: {name} (region: {svc_region})")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'run', 'services', 'delete', name, '--region', svc_region, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Cloud Run Jobs
    if resources.get('cloud_run_jobs'):
        print("\n🗑️  Deleting Cloud Run Jobs...")
        sys.stdout.flush()
        for job in resources['cloud_run_jobs']:
            name = job.get('name')
            job_region = job.get('region', region)
            if name:
                print(f"  Deleting Cloud Run Job: {name} (region: {job_region})")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'run', 'jobs', 'delete', name, '--region', job_region, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Cloud Scheduler jobs
    if resources.get('cloud_scheduler_jobs'):
        print("\n🗑️  Deleting Cloud Scheduler jobs...")
        sys.stdout.flush()
        for job in resources['cloud_scheduler_jobs']:
            name = job.get('name')
            # Extract job name from URL if it's a full URL
            if name and '/jobs/' in name:
                name = name.split('/jobs/')[-1].split(':')[0]
            job_region = job.get('region', region)
            if name:
                print(f"  Deleting Scheduler job: {name} (region: {job_region})")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'scheduler', 'jobs', 'delete', name, '--location', job_region, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Cloud Build triggers
    if resources.get('cloud_build_triggers'):
        print("\n🗑️  Deleting Cloud Build triggers...")
        sys.stdout.flush()
        for trigger in resources['cloud_build_triggers']:
            name = trigger.get('name')
            if name:
                print(f"  Deleting Cloud Build trigger: {name}")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'builds', 'triggers', 'delete', name, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Pub/Sub topics
    if resources.get('pubsub_topics'):
        print("\n🗑️  Deleting Pub/Sub topics...")
        sys.stdout.flush()
        for topic in resources['pubsub_topics']:
            name = topic.get('name')
            if name:
                print(f"  Deleting Pub/Sub topic: {name}")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'pubsub', 'topics', 'delete', name, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Cloud SQL instances
    if resources.get('cloud_sql_instances'):
        print("\n🗑️  Deleting Cloud SQL instances...")
        sys.stdout.flush()
        for instance in resources['cloud_sql_instances']:
            name = instance.get('name')
            if name:
                print(f"  Deleting Cloud SQL instance: {name}")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'sql', 'instances', 'delete', name, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Storage buckets
    if resources.get('storage_buckets'):
        print("\n🗑️  Deleting Storage buckets...")
        sys.stdout.flush()
        for bucket in resources['storage_buckets']:
            name = bucket.get('name')
            if name:
                print(f"  Deleting Storage bucket: {name}")
                sys.stdout.flush()
                # Use gcloud storage rm -r to delete bucket with all contents
                result = subprocess.run(
                    ['gcloud', 'storage', 'rm', '-r', f'gs://{name}', '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Secret Manager secrets
    if resources.get('secret_manager_secrets'):
        print("\n🗑️  Deleting Secret Manager secrets...")
        sys.stdout.flush()
        for secret in resources['secret_manager_secrets']:
            name = secret.get('name')
            if name:
                print(f"  Deleting secret: {name}")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'secrets', 'delete', name, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {name}: {result.stderr}")
                sys.stdout.flush()

    # Delete Service Accounts (last, as they may be used by other resources)
    # Skip deleting the teardown service account itself (can't delete itself)
    if resources.get('service_accounts'):
        print("\n🗑️  Deleting Service Accounts...")
        sys.stdout.flush()
        for sa in resources['service_accounts']:
            email = sa.get('email')
            if email:
                # Skip deleting the teardown service account itself
                if 'deployml-teardown' in email:
                    print(f"  ⏭️  Skipping teardown service account (cannot delete itself): {email}")
                    sys.stdout.flush()
                    continue
                
                print(f"  Deleting service account: {email}")
                sys.stdout.flush()
                result = subprocess.run(
                    ['gcloud', 'iam', 'service-accounts', 'delete', email, '--quiet'],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️  Failed to delete {email}: {result.stderr}")
                sys.stdout.flush()

    print("\n✅ Teardown complete!")
    sys.stdout.flush()
except Exception as e:
    print(f"❌ Error during teardown: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
PYTHON_EOF
