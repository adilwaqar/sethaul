from bedrock_agentcore_starter_toolkit import Runtime
import os
import sys
import json
import logging
from pathlib import Path
from config import config, logger, parse_list_env

codebuild_role = config.codebuild_role_arn
execution_role = config.runtime_role_arn
vpc_security_groups = config.vpc_security_groups
vpc_subnets = config.vpc_subnets
aws_region = config.aws_region


def deploy_agent():
    runtime = Runtime()

    try:
        logger.info("⚙️ Configuring runtime")
        
        try:
            runtime.configure(
                entrypoint='handler.py',
                auto_create_ecr=True,
                protocol="HTTP",
                code_build_execution_role=codebuild_role,
                execution_role=execution_role,
                requirements_file="requirements.txt",
                region=aws_region,
                agent_name='test_harness',
                idle_timeout=180,
                memory_mode='STM_ONLY',
                # Add VPC access for agents to support local tools.
                vpc_enabled=True,
                vpc_subnets=vpc_subnets,
                vpc_security_groups=vpc_security_groups
            )
            logger.info(f"✅ Runtime configured")
        except Exception as e:
            logger.error(f"❌Runtime configuration failed: {e}", exc_info=True)
            return


        logger.info(f"🚀 Launching")
        launch_res = None
        try:
            launch_res = runtime.launch(auto_update_on_conflict=True)
        except Exception as e:
            logger.info(f"❌ Runtime launch failed: {e}", exc_info=True)
            return

        agent_arn = ''

        # Extract ARN from launch response
        if hasattr(launch_res, 'endpoint'):
            agent_arn = launch_res.endpoint.get('agentRuntimeArn', '')
        elif hasattr(launch_res, 'agent_arn'):
            agent_arn = launch_res.agent_arn

        status_response = runtime.status()
        status = status_response.endpoint.get('status', 'UNKNOWN').lower()

        if agent_arn and status == 'ready':
            logger.info(f"✅ Runtime Launched")
    except Exception as e:
        logger.error(f"❌ Deployment error: {e}", exc_info=True)

    finally:
        if runtime:
            try:
                if hasattr(runtime, 'close'):
                    runtime.close()
                elif hasattr(runtime, '__exit__'):
                    runtime.__exit__(None, None, None)
            except Exception as cleanup_err:
                logger.warning(f"Runtime cleanup warning: {cleanup_err}")

if __name__ == "__main__":
    deploy_agent()