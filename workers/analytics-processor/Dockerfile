FROM public.ecr.aws/lambda/python:3.13

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}
RUN uv pip install --system --no-cache -r pyproject.toml

# TODO: Be more picky about what to include to reduce the
# size of the final image + reduce cold start time
COPY . ${LAMBDA_TASK_ROOT}

RUN chmod -R 755 ${LAMBDA_TASK_ROOT}
RUN ls -la ${LAMBDA_TASK_ROOT}

# Add src/ to Python path so jedwal module is importable
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/src:${PYTHONPATH}"

CMD [ "lambdas.analytics_processor.handler.handler" ]
