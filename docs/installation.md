# Installation Guide

Follow these steps in order. Each one builds on the one before it. The commands use `$GCP_PROJECT_ID`, so you set your project ID once and then copy and paste.

## Step 1. Install the prerequisite tools

Install these first:

- [Python 3.11 or newer](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/), installed and running
- [Terraform 1.0 or newer](https://developer.hashicorp.com/terraform/install)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install)

Check that each one is installed:

```bash
python3 --version
docker info          # fails if Docker is not running
terraform version
gcloud --version
```

## Step 2. Sign in and create your GCP project

Sign in to gcloud. You need this before you can create a project.

```bash
gcloud auth login
```

Pick a project ID and save it in your terminal. Every command after this uses it.

```bash
export GCP_PROJECT_ID=deployml-tutorial-yourname
```

!!! note
    - A project ID must be globally unique. Use 6 to 30 lowercase letters, digits, and hyphens.
    - The variable only lasts for this terminal window. If you open a new terminal, run the `export` line again.

Create the project and make it your default:

```bash
gcloud projects create "$GCP_PROJECT_ID"
gcloud config set project "$GCP_PROJECT_ID"
```

You can also create the project in the [GCP Console](https://console.cloud.google.com). If you do, use the same ID in the `export` line above.

Link a billing account. First list your accounts and copy the account ID:

```bash
gcloud billing accounts list
```

Then link it and check the result:

```bash
gcloud billing projects link "$GCP_PROJECT_ID" --billing-account=XXXXXX-XXXXXX-XXXXXX
gcloud billing projects describe "$GCP_PROJECT_ID"
```

The output should include `billingEnabled: true`.

## Step 3. Check your IAM role

If you created the project in step 2, you are the owner and have every role you need. You can skip to step 4. `deployml doctor` checks this again in step 6.

??? info "Using an existing project? Check your roles manually"
    deployml needs `roles/owner`, or all of these roles:

    - `roles/serviceusage.serviceUsageAdmin`
    - `roles/artifactregistry.admin`
    - `roles/cloudsql.admin`
    - `roles/run.admin`
    - `roles/storage.admin`
    - `roles/bigquery.admin`
    - `roles/iam.serviceAccountAdmin`
    - `roles/iam.serviceAccountUser`

    List the roles your account has on the project:

    ```bash
    gcloud projects get-iam-policy "$GCP_PROJECT_ID" \
      --flatten="bindings[].members" \
      --filter="bindings.members:user:$(gcloud config get-value account)" \
      --format="value(bindings.role)"
    ```

    If a role is missing, ask a project owner to grant it:

    ```bash
    gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
      --member="user:YOUR_EMAIL" --role="ROLE_NAME"
    ```

## Step 4. Set up credentials

Run these three commands. Replace `us-west1` with your deploy region if it is different.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GCP_PROJECT_ID"
gcloud auth configure-docker us-west1-docker.pkg.dev
```

- The first command gives Terraform and the client libraries access to your account.
- The second bills BigQuery and client library calls to the right project. If you skip it, the example scripts can fail with `USER_PROJECT_DENIED`.
- The third lets Docker push to Artifact Registry. If you skip it, `deployml build-images` fails with `denied: User cannot access repository`.

## Step 5. Create a project folder and install deployml

!!! tip "Pick your path"
    - **Following the tutorial?** Create a new folder called `deployml-core-tutorial` and work inside it. The commands below do this for you.
    - **Using deployml for your own work?** Create a new folder for your project, or `cd` into an existing one. Then run the same commands from there, skipping the `mkdir` line.

```bash
mkdir deployml-core-tutorial
cd deployml-core-tutorial
python3 -m venv .venv
source .venv/bin/activate
pip install deployml-core
```

Your prompt should now start with `(.venv)`. Activate the environment again each time you open a new terminal. On Windows, see the notes at the bottom of this page.

Check that the install worked:

```bash
deployml --help
```

## Step 6. Verify your setup

```bash
deployml doctor --project-id "$GCP_PROJECT_ID"
```

The doctor checks:

- Docker and Terraform are installed, and Terraform is 1.0 or newer
- gcloud is signed in, and Application Default Credentials are set
- the `bq` CLI is installed
- the required GCP APIs are enabled
- your IAM roles on the project

!!! note
    On a new project you will see a warning that some required APIs are NOT enabled. This is expected. `deployml init` enables them in the next tutorial. Fix anything else the doctor flags, then run it again.

You are ready to go. Continue to the [tutorials](tutorials/overview.md).

## Platform notes

deployml runs on macOS, Linux, and native Windows. The CLI commands are identical
across all three. The engine detects the operating system and adapts underneath, so
you type the same `deployml` commands everywhere.

??? note "Windows"
    deployml works on native Windows in PowerShell or cmd. A few setup notes keep it
    smooth and let it work out of the box:

    - Toolchain. Install native Windows builds of Python 3.11 or newer, Git for
      Windows, the gcloud SDK, Terraform, and Docker Desktop. For the Kubernetes paths
      also install minikube and run `gcloud components install gke-gcloud-auth-plugin`.
      `deployml doctor` checks the core tools.
    - Python. Install from python.org, then create the virtual environment with the
      launcher, `py -3.11 -m venv .venv`. A bare `python` on a fresh Windows often
      resolves to the Microsoft Store stub, which is not a usable interpreter.
    - Git for Windows is required, not optional. It provides the `bash` that the Cloud
      SQL readiness step runs under during `deployml deploy`. Confirm `bash --version`
      resolves before you deploy.
    - Keep the project and its working directory off OneDrive. OneDrive holds file
      handles open and can make workspace cleanup on `deployml destroy` fail with a
      PermissionError. A path such as `C:\dev\your-project` avoids this.
    - gcloud, bq, and gsutil ship as `.cmd` wrappers on Windows. deployml resolves and
      invokes them correctly for you. If you run gcloud yourself in PowerShell and see
      "running scripts is disabled", call `gcloud.cmd` instead of `gcloud`, or run it
      from cmd.
    - minikube on Windows uses the Docker Desktop driver. The service URL deployml
      prints sits on minikube's internal network and is not reachable from the Windows
      host directly. Reach it with `minikube tunnel`, `minikube service <name> --url`,
      or `kubectl port-forward svc/<name> <local>:<port>`. MLflow on minikube wants at
      least 4 GB, so start with `minikube start --memory=4096 --cpus=2` on a machine
      that can spare it; an 8 GB machine that is also running Docker Desktop and other
      apps may not have room for the MLflow pod.
    - Installing a gcloud component such as the GKE auth plugin with
      `gcloud components install` may, in a non interactive shell, ask you to set
      `CLOUDSDK_PYTHON` first; run `gcloud components copy-bundled-python` and set the
      printed path, or just run the install from an interactive prompt.

??? note "Path syntax across shells"
    - The `export PATH=...` examples in the tutorials are bash. In PowerShell use
      `$env:PATH = "...;" + $env:PATH`. In cmd use `set PATH=...;%PATH%`.

??? note "Docker and line endings"
    - Docker Desktop on Windows uses the WSL2 backend by default. The Cloud Run path
      builds images with Cloud Build and does not need a local Docker daemon, so for
      Cloud Run you can skip local builds. Docker is needed only for the minikube path.
    - If you clone the repo on Windows, the included `.gitattributes` forces shell
      scripts and Dockerfiles to LF line endings. Without this, `docker build` would
      fail inside containers with `exec format error`.
