"""Finite, explicit manual-CI test transport; ordinary/operator defaults stay ECR."""
import os

MODE_KEY = 'AUDIT_CI_TEST_POSTGRES_TRANSPORT'
MODE = 'docker-hub-preloaded-v1'
POSTGRES_ECR = 'public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675'
SUPABASE_ECR = 'public.ecr.aws/supabase/postgres@sha256:21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab'
SERVICE_ECR = 'public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
SELECTED = {POSTGRES_ECR: POSTGRES_ECR.replace('public.ecr.aws/docker/library/', ''),
            SUPABASE_ECR: SUPABASE_ECR.replace('public.ecr.aws/', ''), SERVICE_ECR: SERVICE_ECR}


def require(ok):
    if not ok:
        raise RuntimeError('Unapproved CI test PostgreSQL transport or image reference')


def transport_environment(environment=None):
    """Forward only validated nonsecret mode markers through scrubbed Python children."""
    env = os.environ if environment is None else environment
    if MODE_KEY not in env:
        return {}
    require(type(env.get(MODE_KEY)) is str and env[MODE_KEY] == MODE
            and env.get('CI') == 'true' and env.get('GITHUB_ACTIONS') == 'true'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    return {MODE_KEY: MODE, 'CI': 'true', 'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}


def select_image(reference, environment=None):
    """No arbitrary reference, tag, implicit fallback, credentials or registry rewrite."""
    require(type(reference) is str and reference in SELECTED)
    mode = transport_environment(environment)
    return SELECTED[reference] if mode else reference


def docker_run_arguments(arguments, environment=None):
    """Only selected CI images gain pull-never; default operator argv is unchanged."""
    if not transport_environment(environment):
        return arguments
    require(type(arguments) is list and all(type(value) is str for value in arguments))
    if arguments[:2] != ['docker', 'run'] or not any(value in arguments for value in (SELECTED[POSTGRES_ECR], SELECTED[SUPABASE_ECR])):
        return arguments
    for index, value in enumerate(arguments):
        if value == '--pull':
            require(index + 1 < len(arguments) and arguments[index + 1] == 'never')
        elif value.startswith('--pull='):
            require(value == '--pull=never')
    if '--pull' in arguments or '--pull=never' in arguments:
        return arguments
    return [*arguments[:2], '--pull=never', *arguments[2:]]
