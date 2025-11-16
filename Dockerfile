
FROM arm64v8/python:3.9-alpine


WORKDIR /app


COPY ./requirements.txt /code/requirements.txt


RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt


COPY . .
COPY ./renault_api /renault_api
COPY ./static /static

CMD ["fastapi", "run", "app/main.py", "--port", "80"]