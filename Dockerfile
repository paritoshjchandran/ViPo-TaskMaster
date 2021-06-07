FROM python:3.9
WORKDIR /code
COPY requirements.txt /code/
RUN pip install -r requirements.txt
COPY vipo_tm_exceptions.py /code/
COPY bot_dp.png /code/
COPY tm_main.py /code/