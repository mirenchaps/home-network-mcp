// home-network-mcp/Jenkinsfile
//
// CD pipeline for home-network-mcp.
//
// This file is intentionally thin — all logic lives in the ci-platform
// shared library. The IMAGE_TAG parameter is injected by the GitHub Actions
// CI pipeline when it triggers this Jenkins job after pushing a new image.
//
// Setup steps:
//   1. Register ci-platform as a Jenkins Shared Library (name: 'ci-platform')
//      Jenkins → Manage Jenkins → System → Global Pipeline Libraries
//      Docs: https://www.jenkins.io/doc/book/pipeline/shared-libraries/#global-shared-libraries
//   2. Create a Jenkins Pipeline job pointing at this repo
//   3. Add IMAGE_TAG as a string parameter on the job
//
// @Library pulls the shared library registered in step 1.
// The underscore after _  is required Groovy syntax when using @Library this way.

@Library('ci-platform') _

pipeline {
    agent any

    parameters {
        // IMAGE_TAG is set automatically when GitHub Actions triggers this job.
        // For manual runs, enter the tag you want to deploy (e.g. sha-abc1234).
        string(
            name: 'IMAGE_TAG',
            defaultValue: 'latest',
            description: 'Docker image tag to deploy, e.g. sha-abc1234'
        )
    }

    stages {
        stage('Deploy') {
            steps {
                terraformDeploy(
                    imageTag:       "mirenchaps/home-network-mcp:${params.IMAGE_TAG}",
                    port:           8000,
                    configFilePath: '/etc/home-network-mcp/config.json',
                    sshKeyPath:     '/etc/home-network-mcp/id_ed25519'
                )
            }
        }

        stage('Smoke Test') {
            steps {
                // /metrics is the Prometheus endpoint — a 200 response means
                // the exporter started successfully and is collecting data
                smokeTest(path: '/metrics', port: 8000)
            }
        }
    }

    post {
        success { echo "Deployed home-network-mcp:${params.IMAGE_TAG} successfully" }
        failure { echo "Deployment failed — check Terraform output above" }
    }
}
