# Deploying to Google Cloud Platform (GCP)

You can deploy the CYD Tiled Display Configurator to Google Cloud Run to have an "always up" version accessible from anywhere.

## Prerequisites

1.  **Google Cloud Project**: Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Billing Enabled**: Ensure billing is enabled for your project.
3.  **Cloud SDK**: Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud` CLI) locally, or use the Cloud Shell in the console.
4.  **APIs Enabled**: Enable the Cloud Run and Cloud Build APIs:
    ```bash
    gcloud services enable run.googleapis.com cloudbuild.googleapis.com
    ```

## Option 1: Automated Deployment with Cloud Build

This repository includes a `cloudbuild.yaml` file that automates the build and deployment process.

1.  **Submit the build**:
    Run the following command from the root of the repository:
    ```bash
    gcloud builds submit --config cloudbuild.yaml
    ```

    This command will:
    *   Build the Docker image.
    *   Push it to the Google Container Registry (GCR).
    *   Deploy the image to Cloud Run (service name: `cyd-tiled-display`).

2.  **Access the URL**:
    Once the build finishes, it will output the Service URL (e.g., `https://cyd-tiled-display-xyz-uc.a.run.app`).

## Option 2: Manual Deployment

If you prefer to build and deploy manually:

1.  **Build the image**:
    ```bash
    gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/cyd-tiled-display
    ```
    *(Replace `YOUR_PROJECT_ID` with your actual project ID)*

2.  **Deploy to Cloud Run**:
    ```bash
    gcloud run deploy cyd-tiled-display \
      --image gcr.io/YOUR_PROJECT_ID/cyd-tiled-display \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated
    ```

## Important Considerations

### 1. Persistence (Ephemeral Filesystem)
Cloud Run containers are **stateless**. This means any files written to the filesystem (like generated YAML files in `esphome/`) will be **lost** when the container restarts or scales down.

*   **Usage**: You can use this hosted version to design your screens and generate the YAML configuration.
*   **Saving**: You will need to copy the generated YAML content from the "YAML Preview" or "Code" tab in the UI and save it to your local ESPHome configuration manually.

### 2. Connecting to Home Assistant
Since the server is running on the cloud, it cannot automatically discover your local Home Assistant instance via the Supervisor.

To connect to your Home Assistant:
1.  Ensure your Home Assistant is accessible from the internet (e.g., via Nabu Casa or a public IP/domain).
2.  In the Configurator UI, look for the **Settings** or **Connection** dialog (if available) or use the "Remote HA" features.
3.  You may need to provide your **Home Assistant URL** (e.g., `https://my-ha.ui.nabu.casa`) and a **Long-Lived Access Token**.

### 3. Security
The default deployment command (`--allow-unauthenticated`) makes your configurator accessible to **anyone** with the URL.

*   **Secure it**: It is highly recommended to remove `--allow-unauthenticated` and configure authentication (e.g., using Cloud Run's built-in IAM authentication or putting it behind a load balancer with IAP).
