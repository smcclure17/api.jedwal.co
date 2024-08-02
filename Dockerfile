FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}

RUN pip install -r requirements.txt

# TODO: Be more picky about what to include to reduce the 
# size of the final image + reduce cold start time
COPY . ${LAMBDA_TASK_ROOT}

RUN ls -la ${LAMBDA_TASK_ROOT}

CMD [ "api.handler" ]
