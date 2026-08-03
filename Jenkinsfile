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
                // Deploy both the exporter pod and the MCP server pod.
                // Both use the same image — entrypoint.sh selects the process.
                kubernetesDeploy(
                    deployment: 'home-network-mcp',
                    image:      "mirenchaps/home-network-mcp:${params.IMAGE_TAG}"
                )
                kubernetesDeploy(
                    deployment: 'home-network-mcp-server',
                    image:      "mirenchaps/home-network-mcp:${params.IMAGE_TAG}"
                )
            }
        }

        stage('Smoke Test') {
            steps {
                // Exporter: /metrics on port 30080
                smokeTest(path: '/metrics', port: 30080, host: '192.168.0.38')
                // MCP server: /mcp on port 30081 (streamable-HTTP transport)
                smokeTest(path: '/mcp', port: 30081, host: '192.168.0.38')
            }
        }
    }

    post {
        success { echo "Deployed home-network-mcp:${params.IMAGE_TAG} successfully" }
        failure { echo "Deployment failed — check kubectl output above" }
    }
}
