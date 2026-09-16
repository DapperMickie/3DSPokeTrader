FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml LICENSE README.md ./
COPY poketrader ./poketrader
RUN pip install --no-cache-dir .
EXPOSE 8780
CMD ["poke-trader", "relay", "--bind", "0.0.0.0", "--credential-file", "/data/relay-credential"]
