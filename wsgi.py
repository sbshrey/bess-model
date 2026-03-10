import os
from bess_model.web.app import create_app

config_path = os.environ.get("BESS_CONFIG_PATH", "config.example.yaml")
app = create_app(config_path=config_path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
