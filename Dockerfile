
FROM arm64v8/python:3.12-alpine


WORKDIR /app


COPY ./requirements.txt /code/requirements.txt


RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt


COPY . .
COPY ./static /static

CMD ["fastapi", "run", "app/main.py", "--port", "80"]