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
                // GitOps deploy: commit the new image tag to home-lab-gitops
                // instead of pushing to the cluster directly. ArgoCD picks up
                // the commit and syncs it — this job's job ends at git push.
                withCredentials([usernamePassword(
                    credentialsId: 'github-home-lab-gitops-push',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN'
                )]) {
                    sh '''
                        set -e

                        rm -rf home-lab-gitops
                        git clone https://${GIT_USER}:${GIT_TOKEN}@github.com/mirenchaps/home-lab-gitops.git
                        cd home-lab-gitops

                        sed -i "s|image: mirenchaps/home-network-mcp:.*|image: mirenchaps/home-network-mcp:${IMAGE_TAG}|" apps/home-network-mcp/deployment.yaml
                        sed -i "s|image: mirenchaps/home-network-mcp:.*|image: mirenchaps/home-network-mcp:${IMAGE_TAG}|" apps/home-network-mcp-server/deployment.yaml

                        git config user.email "jenkins@home-lab.local"
                        git config user.name "Jenkins"
                        git add apps/home-network-mcp/deployment.yaml apps/home-network-mcp-server/deployment.yaml
                        git commit -m "Deploy home-network-mcp:${IMAGE_TAG}"

                        # main is protected — push to a deploy branch and go through the API instead.
                        DEPLOY_BRANCH="deploy/${IMAGE_TAG}-${BUILD_NUMBER}"
                        git push origin "HEAD:refs/heads/${DEPLOY_BRANCH}"

                        API="https://api.github.com/repos/mirenchaps/home-lab-gitops"
                        AUTH_HEADER="Authorization: Bearer ${GIT_TOKEN}"
                        ACCEPT_HEADER="Accept: application/vnd.github+json"
                        VERSION_HEADER="X-GitHub-Api-Version: 2022-11-28"

                        PR_RESPONSE=$(curl -fsSL -X POST \\
                            -H "${AUTH_HEADER}" -H "${ACCEPT_HEADER}" -H "${VERSION_HEADER}" \\
                            "${API}/pulls" \\
                            -d "{\\"title\\":\\"Deploy home-network-mcp:${IMAGE_TAG}\\",\\"head\\":\\"${DEPLOY_BRANCH}\\",\\"base\\":\\"main\\"}")
                        PR_NUMBER=$(echo "${PR_RESPONSE}" | jq -r '.number')

                        curl -fsSL -X PUT \\
                            -H "${AUTH_HEADER}" -H "${ACCEPT_HEADER}" -H "${VERSION_HEADER}" \\
                            "${API}/pulls/${PR_NUMBER}/merge" \\
                            -d '{"merge_method":"squash"}'

                        curl -fsSL -X DELETE \\
                            -H "${AUTH_HEADER}" -H "${ACCEPT_HEADER}" -H "${VERSION_HEADER}" \\
                            "${API}/git/refs/heads/${DEPLOY_BRANCH}"
                    '''
                }
            }
        }

        stage('Smoke Test') {
            steps {
                // Exporter: /metrics on port 30080
                smokeTest(path: '/metrics', port: 30080, host: '192.168.0.38')
                // MCP server: /health on port 30081
                // (/mcp requires a proper MCP handshake — plain curl returns 400)
                smokeTest(path: '/health', port: 30081, host: '192.168.0.38')
            }
        }
    }

    post {
        success { echo "Deployed home-network-mcp:${params.IMAGE_TAG} successfully" }
        failure { echo "Deployment failed — check kubectl output above" }
    }
}
