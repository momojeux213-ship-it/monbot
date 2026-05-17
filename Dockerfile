FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libaudioop-dev
COPY requirements.txt .
RUN pip install discord.py python-dotenv
COPY . .
CMD ["python", "bot.py"]
